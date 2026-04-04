//! Remote Control Relay - Rust Implementation (clean architecture)
//! Key patterns: tokio::sync::RwLock + mpsc::Sender for connection writers

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use futures_util::{SinkExt, StreamExt};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::RwLock as SyncRwLock;
use tokio::sync::mpsc;
use tokio_tungstenite::{accept_async, tungstenite::Message};
use tracing::info;

#[derive(Clone)]
struct AppState {
    agents: Arc<SyncRwLock<HashMap<String, AgentEntry>>>,
    clients: Arc<SyncRwLock<HashMap<String, ClientEntry>>>,
    password: String,
    start_time: Instant,
}

struct AgentEntry {
    tx: mpsc::Sender<Message>,
    agent_id: String,
    hostname: String,
    os: String,
    last_seen: Instant,
}

struct ClientEntry {
    tx: mpsc::Sender<Message>,
    agent_id: Option<String>,
    last_seen: Instant,
}

fn http_response(status: u16, body: &str) -> String {
    format!(
        "HTTP/1.1 {} {}\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: {}\r\n\r\n{}",
        status,
        match status { 200 => "OK", 401 => "Unauthorized", 404 => "Not Found", _ => "OK" },
        body.len(),
        body
    )
}

async fn handle_http(state: AppState, stream: &mut TcpStream, path: &str, auth: Option<&str>) {
    let agents = state.agents.read().await;
    let clients = state.clients.read().await;

    let resp = match path {
        "/api/agents" => {
            let mut authorized = false;
            if let Some(auth) = auth {
                if auth.starts_with("Bearer ") {
                    let token = &auth[7..];
                    use base64::Engine as _;
                    if let Ok(decoded) = base64::engine::general_purpose::STANDARD.decode(token) {
                        if let Ok(pw) = String::from_utf8(decoded) {
                            authorized = pw == state.password;
                        }
                    }
                }
            }
            if !authorized {
                http_response(401, r#"{"error":"Unauthorized"}"#)
            } else {
                let list: Vec<_> = agents.iter().map(|(id, a)| {
                    serde_json::json!({
                        "agentId": id,
                        "hostname": a.hostname,
                        "os": a.os,
                        "lastSeen": a.last_seen.elapsed().as_millis() as i64,
                        "online": true
                    })
                }).collect();
                let body = serde_json::json!({ "agents": list }).to_string();
                http_response(200, &body)
            }
        }
        "/api/status" => {
            let body = serde_json::json!({
                "status": "online",
                "uptime": state.start_time.elapsed().as_secs_f64(),
                "agents": agents.len(),
                "clients": clients.len(),
                "version": "0.1.0-rust"
            }).to_string();
            http_response(200, &body)
        }
        "/" => {
            let body = format!(
                r#"<html><body><h1>Remote Control Relay v0.1-rust</h1><p>Online</p><p>Agents: {}</p><p>Clients: {}</p><p>Uptime: {:.0}s</p></body></html>"#,
                agents.len(), clients.len(), state.start_time.elapsed().as_secs_f64()
            );
            format!(
                "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {}\r\n\r\n{}",
                body.len(), body
            )
        }
        _ => http_response(404, r#"{"error":"Not Found"}"#),
    };

    stream.write_all(resp.as_bytes()).await.ok();
}

async fn handle_agent(state: AppState, stream: TcpStream) {
    let ws = match accept_async(stream).await {
        Ok(ws) => ws,
        Err(e) => { tracing::warn!("WS accept error: {}", e); return; }
    };
    let (mut ws_tx, mut ws_rx) = ws.split();
    let (tx, mut rx) = mpsc::channel::<Message>(32);

    let aid = loop {
        if let Some(Ok(Message::Text(text))) = ws_rx.next().await {
            if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&text) {
                if parsed["type"] == "auth" {
                    let aid = parsed["agent_id"].as_str().unwrap_or("").to_string();
                    let hostname = parsed["hostname"].as_str().unwrap_or("?").to_string();
                    let os = parsed["os"].as_str().unwrap_or("?").to_string();
                    info!("[Agent] Auth: {} ({})", aid, hostname);
                    let _ = ws_tx.send(Message::Text(r#"{"type":"auth_ok"}"#.into())).await;
                    state.agents.write().await.insert(aid.clone(), AgentEntry {
                        tx: tx.clone(),
                        agent_id: aid.clone(),
                        hostname,
                        os,
                        last_seen: Instant::now(),
                    });
                    break aid;
                }
            }
        } else { return; }
    };

    let writer_task = tokio::spawn(async move {
        while let Some(msg) = rx.recv().await {
            if ws_tx.send(msg).await.is_err() { break; }
        }
    });

    loop {
        tokio::select! {
            msg = ws_rx.next() => {
                match msg {
                    Some(Ok(Message::Text(text))) => {
                        if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&text) {
                            let t = parsed["type"].as_str().unwrap_or("");
                            {
                                let mut agents = state.agents.write().await;
                                if let Some(a) = agents.get_mut(&aid) {
                                    a.last_seen = Instant::now();
                                }
                            }
                            if t == "screen" || t == "output" || t == "exec_result" || t == "shell_result" || t == "file_chunk" {
                                let data = parsed.to_string();
                                let clients = state.clients.read().await;
                                for (_, c) in clients.iter() {
                                    if c.agent_id.as_ref() == Some(&aid) {
                                        c.tx.send(Message::Text(data.clone().into())).await.ok();
                                    }
                                }
                            }
                        }
                    }
                    Some(Ok(Message::Close(_))) | None => break,
                    _ => {}
                }
            }
            _ = tokio::time::sleep(std::time::Duration::from_secs(30)) => {
                let timed_out = {
                    let agents = state.agents.read().await;
                    agents.get(&aid).map_or(false, |a| a.last_seen.elapsed() > std::time::Duration::from_secs(120))
                };
                if timed_out {
                    info!("[Agent] {} heartbeat timeout", aid);
                    break;
                }
            }
        }
    }

    writer_task.abort();
    state.agents.write().await.remove(&aid);
    info!("[Agent] {} disconnected", aid);
}

async fn handle_client(state: AppState, stream: TcpStream) {
    let ws = match accept_async(stream).await {
        Ok(ws) => ws,
        Err(e) => { tracing::warn!("WS accept error: {}", e); return; }
    };
    let (mut ws_tx, mut ws_rx) = ws.split();
    let (tx, mut rx) = mpsc::channel::<Message>(32);

    loop {
        if let Some(Ok(Message::Text(text))) = ws_rx.next().await {
            if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&text) {
                if parsed["type"] == "auth" {
                    if parsed["password"].as_str().unwrap_or("") != state.password {
                        let _ = ws_tx.send(Message::Text(r#"{"type":"error","message":"Invalid password"}"#.into())).await;
                        return;
                    }
                    let _ = ws_tx.send(Message::Text(r#"{"type":"auth_ok"}"#.into())).await;
                    break;
                }
            }
        } else { return; }
    }

    let cid = uuid::Uuid::new_v4().to_string();
    state.clients.write().await.insert(cid.clone(), ClientEntry {
        tx: tx.clone(),
        agent_id: None,
        last_seen: Instant::now(),
    });

    let writer_task = tokio::spawn(async move {
        while let Some(msg) = rx.recv().await {
            if ws_tx.send(msg).await.is_err() { break; }
        }
    });

    loop {
        tokio::select! {
            msg = ws_rx.next() => {
                match msg {
                    Some(Ok(Message::Text(text))) => {
                        if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&text) {
                            let t = parsed["type"].as_str().unwrap_or("");
                            if t == "input" || t == "clipboard" || t == "file_request" || t == "exec" || t == "shell" || t == "req_kf" {
                                if let Some(c) = state.clients.read().await.get(&cid) {
                                    if let Some(aid) = &c.agent_id {
                                        if let Some(a) = state.agents.read().await.get(aid) {
                                            let out = parsed.to_string();
                                            a.tx.send(Message::Text(out.into())).await.ok();
                                        }
                                    }
                                }
                            } else if t == "subscribe" {
                                if let Some(aid) = parsed["agent_id"].as_str() {
                                    if state.agents.read().await.contains_key(aid) {
                                        if let Some(c) = state.clients.write().await.get_mut(&cid) {
                                            c.agent_id = Some(aid.to_string());
                                        }
                                        // Send through mpsc to avoid ws_tx double-move
                                        tx.send(Message::Text(r#"{"type":"subscribed"}"#.into())).await.ok();
                                    }
                                }
                            }
                            if let Some(c) = state.clients.write().await.get_mut(&cid) {
                                c.last_seen = Instant::now();
                            }
                        }
                    }
                    Some(Ok(Message::Close(_))) | None => break,
                    _ => {}
                }
            }
            _ = tokio::time::sleep(std::time::Duration::from_secs(30)) => {
                let timed_out = {
                    let clients = state.clients.read().await;
                    clients.get(&cid).map_or(false, |c| c.last_seen.elapsed() > std::time::Duration::from_secs(120))
                };
                if timed_out {
                    info!("[Client] {} heartbeat timeout", cid);
                    break;
                }
            }
        }
    }

    writer_task.abort();
    state.clients.write().await.remove(&cid);
    info!("[Client] {} disconnected", cid);
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    tracing_subscriber::fmt().init();
    let state = AppState {
        agents: Arc::new(RwLock::new(HashMap::new())),
        clients: Arc::new(RwLock::new(HashMap::new())),
        password: std::env::var("ACCESS_PASSWORD").unwrap_or_else(|_| "Ops@2024!".to_string()),
        start_time: Instant::now(),
    };
    let port = std::env::var("PORT").unwrap_or_else(|_| "21112".to_string());
    let addr = format!("0.0.0.0:{}", port);
    let listener = TcpListener::bind(&addr).await?;
    info!("Remote Control Relay v0.1-rust listening on {}", addr);

    loop {
        if let Ok((stream, _)) = listener.accept().await {
            let state = state.clone();
            tokio::spawn(async move {
                let mut buf = [0u8; 2048];
                let n = match stream.peek(&mut buf).await {
                    Ok(n) if n > 0 => n,
                    _ => return,
                };
                let request = match std::str::from_utf8(&buf[..n]) {
                    Ok(s) => s.to_string(),
                    Err(_) => return,
                };
                let is_ws = request.contains("Upgrade: websocket");
                let path = request.lines().next()
                    .and_then(|l| l.split_whitespace().nth(1))
                    .unwrap_or("/")
                    .to_string();
                let auth = request.lines()
                    .find(|l| l.to_lowercase().starts_with("authorization:"))
                    .and_then(|l| l.split(':').nth(1))
                    .map(str::trim);

                let mut stream = stream;
                stream.read(&mut buf).await.ok();

                if is_ws {
                    match path.as_str() {
                        "/agent" => handle_agent(state, stream).await,
                        "/client" => handle_client(state, stream).await,
                        _ => {}
                    }
                } else {
                    handle_http(state, &mut stream, &path, auth).await;
                }
            });
        }
    }
}