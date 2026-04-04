//! Remote Control Relay - Axum Implementation
//! Uses Axum WebSocket which is compatible with nginx reverse proxy

use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Instant;

use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        State,
    },
    routing::{get, on, MethodFilter},
    Router,
};
use axum::response::Response;
use futures_util::{SinkExt, StreamExt};
use serde::Serialize;
use tokio::sync::RwLock;
use tower_http::cors::{Any, CorsLayer};
use tracing::info;

#[derive(Clone)]
struct AppState {
    agents: Arc<RwLock<HashMap<String, AgentEntry>>>,
    clients: Arc<RwLock<HashMap<String, ClientEntry>>>,
    password: String,
    start_time: Instant,
}

struct AgentEntry {
    tx: tokio::sync::mpsc::Sender<Message>,
    #[allow(dead_code)]
    agent_id: String, // kept for potential debug logging
    hostname: String,
    os: String,
    last_seen: Instant,
}

struct ClientEntry {
    tx: tokio::sync::mpsc::Sender<Message>,
    agent_id: Option<String>,
    last_seen: Instant,
}

#[derive(Serialize)]
struct StatusResponse {
    status: String,
    uptime: f64,
    agents: usize,
    clients: usize,
    version: &'static str,
}

#[derive(Serialize)]
struct AgentListResponse {
    agents: Vec<AgentInfo>,
}

#[derive(Serialize)]
struct AgentInfo {
    agent_id: String,
    hostname: String,
    os: String,
    last_seen: i64,
    online: bool,
}

async fn handle_status(State(state): State<AppState>) -> axum::Json<StatusResponse> {
    let agents = state.agents.read().await;
    let clients = state.clients.read().await;
    axum::Json(StatusResponse {
        status: "online".into(),
        uptime: state.start_time.elapsed().as_secs_f64(),
        agents: agents.len(),
        clients: clients.len(),
        version: "0.2.0-axum",
    })
}

async fn handle_agents(State(state): State<AppState>) -> axum::Json<AgentListResponse> {
    let agents = state.agents.read().await;
    let list: Vec<AgentInfo> = agents
        .iter()
        .map(|(id, a)| AgentInfo {
            agent_id: id.clone(),
            hostname: a.hostname.clone(),
            os: a.os.clone(),
            last_seen: a.last_seen.elapsed().as_millis() as i64,
            online: true,
        })
        .collect();
    axum::Json(AgentListResponse { agents: list })
}

async fn handle_agent_ws(
    State(state): State<AppState>,
    ws: WebSocketUpgrade,
) -> Response {
    let state = state.clone();
    ws.on_upgrade(move |socket| {
        let state = state.clone();
        async move {
            handle_agent_socket(state, socket).await;
        }
    })
}

async fn handle_agent_socket(state: AppState, socket: WebSocket) {
    let (mut sender, mut receiver) = socket.split();
    let (tx, mut rx) = tokio::sync::mpsc::channel::<Message>(32);

    let aid = loop {
        if let Some(msg) = receiver.next().await {
            match msg {
                Ok(Message::Text(text)) => {
                    if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&text) {
                        if parsed["type"] == "auth" {
                            let aid = parsed["agent_id"].as_str().unwrap_or("").to_string();
                            let hostname = parsed["hostname"].as_str().unwrap_or("?").to_string();
                            let os = parsed["os"].as_str().unwrap_or("?").to_string();
                            info!("[Agent] Auth: {} ({})", aid, hostname);
                            let _ = sender.send(Message::Text(r#"{"type":"auth_ok"}"#.into())).await;
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
                }
                Ok(Message::Close(_)) | Err(_) => return,
                _ => {}
            }
        } else {
            return;
        }
    };

    let writer_task = tokio::spawn(async move {
        while let Some(msg) = rx.recv().await {
            if sender.send(msg).await.is_err() {
                break;
            }
        }
    });

    loop {
        tokio::select! {
            msg = receiver.next() => {
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

async fn handle_client_ws(
    State(state): State<AppState>,
    ws: WebSocketUpgrade,
) -> Response {
    let state = state.clone();
    ws.on_upgrade(move |socket| {
        let state = state.clone();
        async move {
            handle_client_socket(state, socket).await;
        }
    })
}

async fn handle_client_socket(state: AppState, socket: WebSocket) {
    let (mut sender, mut receiver) = socket.split();
    let (tx, mut rx) = tokio::sync::mpsc::channel::<Message>(32);

    // Auth
    loop {
        if let Some(msg) = receiver.next().await {
            match msg {
                Ok(Message::Text(text)) => {
                    if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&text) {
                        if parsed["type"] == "auth" {
                            if parsed["password"].as_str().unwrap_or("") != state.password {
                                let _ = sender.send(Message::Text(r#"{"type":"error","message":"Invalid password"}"#.into())).await;
                                return;
                            }
                            let _ = sender.send(Message::Text(r#"{"type":"auth_ok"}"#.into())).await;
                            break;
                        }
                    }
                }
                Ok(Message::Close(_)) | Err(_) => return,
                _ => {}
            }
        } else {
            return;
        }
    }

    let cid = uuid::Uuid::new_v4().to_string();
    state.clients.write().await.insert(cid.clone(), ClientEntry {
        tx: tx.clone(),
        agent_id: None,
        last_seen: Instant::now(),
    });

    let writer_task = tokio::spawn(async move {
        while let Some(msg) = rx.recv().await {
            if sender.send(msg).await.is_err() {
                break;
            }
        }
    });

    loop {
        tokio::select! {
            msg = receiver.next() => {
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
    tracing_subscriber::fmt()
        .with_max_level(tracing::Level::INFO)
        .init();

    let password = std::env::var("ACCESS_PASSWORD").unwrap_or_else(|_| "WeiChao_2026Ctrl!".to_string());
    let port: u16 = std::env::var("PORT")
        .unwrap_or_else(|_| "21112".to_string())
        .parse()
        .unwrap_or(21112);

    let state = AppState {
        agents: Arc::new(RwLock::new(HashMap::new())),
        clients: Arc::new(RwLock::new(HashMap::new())),
        password,
        start_time: Instant::now(),
    };

    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    let app = Router::new()
        .route("/api/status", get(handle_status))
        .route("/api/agents", get(handle_agents))
        .route("/agent", on(MethodFilter::GET, handle_agent_ws))
        .route("/client", on(MethodFilter::GET, handle_client_ws))
        .route("/", get(|| async { "Remote Control Relay v0.2-axum" }))
        .layer(cors)
        .with_state(state);

    let addr = SocketAddr::from(([0, 0, 0, 0], port));
    info!("Remote Control Relay v0.2-axum listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
