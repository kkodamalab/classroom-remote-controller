# Protocol v1

PeerServer carries OFFER/ANSWER/CANDIDATE only. Reliable ordered WebRTC DataChannel carries UTF-8 JSON (PeerJS serialization `raw`). No media tracks.

QR URL fragment: `id`, `token`, `expires` (Unix seconds), `host`, `port`, `path`, `key`. Fragment is cleared from browser history after parsing. Token is 256 random bits, session ID 192 random bits. Pairing expires after 5 minutes; approved session expires after 2 hours.

Client hello: `{type:"hello",token,device}`. Desktop requires local approval; replies `{type:"approved"}`. Commands only after approval: `{type:"command",seq:1,profile:"powerpoint",action:"next",args:{}}`. Sequence strictly increases; invalid or failed commands consume their sequence. Desktop returns `{type:"result",seq,ok,code}`. Sending is not execution confirmation. Ping/pong every 3 seconds; 12 seconds silence revokes session. Any disconnect, rejection or emergency stop revokes token; reconnect requires a new QR and approval. One candidate/phone per session.

All envelopes have strict fields and length bounds. Rate limit: 30 messages/s, burst 40; commands 20/s, burst 25. Mouse relative deltas limited to ±40 pixels and scroll ±3 per command. No arbitrary text, executable paths, shell commands, file payloads or screen capture.
