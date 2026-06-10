"""WS relay protocol contract — agent <-> VPS relay <-> web client.

This file is the single source of truth for the on-the-wire JSON message
shapes between the Python Windows Agent and the Node VPS relay
(`server/index.js`). Any field-shape change must be reflected here AND
the implementation on both sides, or we get the kind of silent half-dead
bugs we hit on 2026-06-10 (server stopped echoing keepalive_ack.seq and
the agent's probe matcher silently rejected every ack).

Conventions
-----------
* Transport: JSON over WebSocket text frames (opcode 0x1).
* All field names are snake_case.
* Every message has a ``type`` field; consumers dispatch on that first.
* Field requirements are noted as REQUIRED / OPTIONAL / ECHO.

.. warning::
    The server's keepalive_ack contract was historically lax (only
    ``ts`` was echoed). Both sides now strictly follow the contract,
    but agents still keep a ts-window fallback for forward
    compatibility with pre-contract servers in staging / old
    deployments.

Message catalogue
-----------------

Agent -> Server (outbound from agent)

* ``auth``  — REQUIRED
    ``{"type": "auth", "agentId": str, "secret": str,
       "hostname": str, "os": str}``

* ``keepalive``  — REQUIRED
    ``{"type": "keepalive", "seq": int, "ts": float}``
    ``ts`` is the agent's time.time() at send; server echoes it back
    in keepalive_ack so the agent can measure round-trip latency.

* ``screen``  — REQUIRED for screen streaming
    ``{"type": "screen", "fmt": "kf"|"df", "data": base64,
       "w": int, "h": int, "regions"?: [[x,y,w,h], ...],
       "seq": int, "ts": float, "server_ts_ms": int}``

* ``output``  — REQUIRED for shell exec
    ``{"type": "output", "session": str, "data": str, "done": bool}``

* ``file_chunk``  — REQUIRED for file upload streaming

* ``pong``  — REQUIRED to refresh server-side lastSeen
    ``{"type": "pong", "ts": int}``

* ``input_ack``  — REQUIRED for input liveness probe (server->agent)
    ``{"type": "input_ack", "lastSeenSeq": int}``

Server -> Agent (inbound to agent)

* ``auth_ok``  — REQUIRED on successful auth
    ``{"type": "auth_ok", "agentId": str}``

* ``auth_failed``  — REQUIRED on bad agentId/secret
    ``{"type": "auth_failed", "reason": str}``

* ``keepalive_ack``  — REQUIRED, CONTRACT-CRITICAL
    ``{"type": "keepalive_ack", "seq": int, "ts": float}``
    **Server MUST echo back both the seq and ts the agent sent.**
    The agent's probe matcher relies on seq for unambiguous
    round-trip matching. Older server versions omitted seq, which
    forced the agent to time out and force-reconnect every 5s.
    Agent still falls back to a ts-window match if seq is absent,
    but treat missing-seq as a server bug.

* ``ping``  — OPTIONAL websocket-level ping (server-initiated)
    The Python agent's websocket-client auto-responds with pong; no
    app-level handling needed.

* ``mouse``  — REQUIRED for remote mouse input
    ``{"type": "mouse", "x": int, "y": int, "button": int,
       "action": "down"|"up"|"move"|"click"|"double_click"|"wheel",
       "seq": int}``
    The ``seq`` field is used by the server's _isAgentLive check to
    detect a half-dead ws within 5s instead of waiting for the
    keepalive timeout.

* ``key``  — REQUIRED for remote keyboard input
    ``{"type": "key", "key": str, "action": "down"|"up", "seq": int}``

* ``hotkey``  — REQUIRED for hotkey combos
    ``{"type": "hotkey", "keys": [str, ...], "seq": int}``

* ``type``  — REQUIRED for text typing
    ``{"type": "type", "text": str, "seq": int}``

* ``clipboard_set``  — REQUIRED for clipboard sync
    ``{"type": "clipboard_set", "text": str, "seq": int}``

* ``agent_offline`` / ``client_connected`` / ``client_disconnected`` /
  ``error``  — control-plane notifications (lifecycle / debug).

Keepalive contract details
--------------------------
The ``keepalive`` / ``keepalive_ack`` pair is the liveness signal for
the *agent->server* half of the connection. The server independently
gates *server->agent* liveness on the input_ack pattern (see
input_ack above), so a half-dead socket in either direction gets
detected within ~5s.

The 5s window comes from:
- Agent sends keepalive every 25s; server must ack within 5s.
- Server's relay layer drops input msgs whose seq is more than
  ``INPUT_SEQ_LIVENESS_WINDOW_S`` (5s default) behind the highest
  seq the agent has acked.

If you change either window, update both ends of the protocol and
this docstring.

Versioning
----------
This protocol is implicit-versioned by field presence. Adding a new
OPTIONAL field is backward-compatible. Removing or renaming a
REQUIRED field is a breaking change and requires a coordinated
deploy (server first, with a fallback that ignores the missing
field; then agent).
"""

# Constants pulled here so production code can refer to message types
# without stringly-typed typos.

# Agent -> Server
WS_TYPE_AUTH         = 'auth'
WS_TYPE_KEEPALIVE    = 'keepalive'
WS_TYPE_SCREEN       = 'screen'
WS_TYPE_OUTPUT       = 'output'
WS_TYPE_FILE_CHUNK   = 'file_chunk'
WS_TYPE_PONG         = 'pong'
WS_TYPE_INPUT_ACK    = 'input_ack'
WS_TYPE_BYE          = 'bye'

# Server -> Agent (round-trip / control)
WS_TYPE_AUTH_OK      = 'auth_ok'
WS_TYPE_AUTH_FAILED  = 'auth_failed'
WS_TYPE_KEEPALIVE_ACK = 'keepalive_ack'
WS_TYPE_AGENT_OFFLINE = 'agent_offline'
WS_TYPE_CLIENT_CONNECTED = 'client_connected'
WS_TYPE_CLIENT_DISCONNECTED = 'client_disconnected'
WS_TYPE_ERROR        = 'error'

# Server -> Agent (commands from remote clients)
WS_TYPE_MOUSE        = 'mouse'
WS_TYPE_KEY          = 'key'
WS_TYPE_HOTKEY       = 'hotkey'
WS_TYPE_TYPE         = 'type'
WS_TYPE_CLIPBOARD_SET = 'clipboard_set'
WS_TYPE_EXEC         = 'exec'
WS_TYPE_FILE_REQUEST = 'file_request'

# Keepalive tunables. Keep these in sync with server/index.js
# (HeartbeatInterval / KeepaliveAckTimeout in the relay config).
KEEPALIVE_INTERVAL_S = 25.0
KEEPALIVE_ACK_TIMEOUT_S = 5.0
# How long the agent keeps a ts value in its fallback window before
# pruning. Must be at least 6 * ack_timeout to cover the 3-fail
# force-reconnect window.
KEEPALIVE_TS_WINDOW_S = 30.0
# Max samples for the rolling RTT list surfaced in the service
# heartbeat log.
KEEPALIVE_RTT_WINDOW = 20