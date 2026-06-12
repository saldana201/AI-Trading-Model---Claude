(globalThis["TURBOPACK"] || (globalThis["TURBOPACK"] = [])).push([typeof document === "object" ? document.currentScript : undefined,
"[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "default",
    ()=>Chat
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$build$2f$polyfills$2f$process$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = /*#__PURE__*/ __turbopack_context__.i("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/build/polyfills/process.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/compiled/react/index.js [app-client] (ecmascript)");
;
var _s = __turbopack_context__.k.signature();
"use client";
;
const API = __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$build$2f$polyfills$2f$process$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["default"].env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
function Chat() {
    _s();
    const [messages, setMessages] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])([]);
    const [input, setInput] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])("");
    const [busy, setBusy] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(false);
    const boxRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useRef"])(null);
    async function send(e) {
        e?.preventDefault();
        const text = input.trim();
        if (!text || busy) return;
        setInput("");
        const next = [
            ...messages,
            {
                role: "user",
                text
            }
        ];
        setMessages(next);
        setBusy(true);
        try {
            const r = await fetch(`${API}/api/chat`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    message: text
                })
            });
            const data = await r.json();
            setMessages([
                ...next,
                {
                    role: "assistant",
                    text: data.reply,
                    mode: data.mode
                }
            ]);
        } catch  {
            setMessages([
                ...next,
                {
                    role: "assistant",
                    text: "API unreachable — start it with: uvicorn apps.api.main:app --port 8000"
                }
            ]);
        } finally{
            setBusy(false);
            queueMicrotask(()=>boxRef.current?.scrollTo(0, 1e9));
        }
    }
    const suggestions = [
        "What is the market regime today?",
        "Key QQQ and SPY levels",
        "Calls, puts, or no trade?",
        "Which sectors are leading?"
    ];
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
        className: "card",
        style: {
            marginTop: 18
        },
        "aria-label": "Chat",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                children: "Ask Confluence"
            }, void 0, false, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                lineNumber: 49,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                ref: boxRef,
                className: "chatbox",
                children: [
                    messages.length === 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "empty",
                        children: [
                            "Ask about the regime, levels, sectors, setups, extension, gamma…",
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "sugg",
                                children: suggestions.map((s)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                        className: "chip",
                                        type: "button",
                                        onClick: ()=>{
                                            setInput(s);
                                        },
                                        children: s
                                    }, s, false, {
                                        fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                                        lineNumber: 56,
                                        columnNumber: 17
                                    }, this))
                            }, void 0, false, {
                                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                                lineNumber: 54,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                        lineNumber: 52,
                        columnNumber: 11
                    }, this),
                    messages.map((m, i)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: `msg ${m.role}`,
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    className: "who",
                                    children: m.role === "user" ? "you" : `confluence${m.mode === "deterministic" ? " · deterministic" : ""}`
                                }, void 0, false, {
                                    fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                                    lineNumber: 64,
                                    columnNumber: 13
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                    children: m.text
                                }, void 0, false, {
                                    fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                                    lineNumber: 65,
                                    columnNumber: 13
                                }, this)
                            ]
                        }, i, true, {
                            fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                            lineNumber: 63,
                            columnNumber: 11
                        }, this)),
                    busy && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "msg assistant",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "who",
                                children: "confluence"
                            }, void 0, false, {
                                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                                lineNumber: 68,
                                columnNumber: 49
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                children: "…"
                            }, void 0, false, {
                                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                                lineNumber: 68,
                                columnNumber: 88
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                        lineNumber: 68,
                        columnNumber: 18
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                lineNumber: 50,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("form", {
                className: "chatrow",
                onSubmit: send,
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                        value: input,
                        onChange: (e)=>setInput(e.target.value),
                        placeholder: "What level invalidates the NVDA trade?",
                        "aria-label": "Message"
                    }, void 0, false, {
                        fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                        lineNumber: 71,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        type: "submit",
                        disabled: busy,
                        children: "Send"
                    }, void 0, false, {
                        fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                        lineNumber: 73,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                lineNumber: 70,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
        lineNumber: 48,
        columnNumber: 5
    }, this);
}
_s(Chat, "25yhsYil/HDSS5GVVr/KIY01hVo=");
_c = Chat;
var _c;
__turbopack_context__.k.register(_c, "Chat");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "ArmButton",
    ()=>ArmButton,
    "LiveFeed",
    ()=>LiveFeed,
    "LiveTicker",
    ()=>LiveTicker,
    "SnapshotRefresher",
    ()=>SnapshotRefresher
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$build$2f$polyfills$2f$process$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = /*#__PURE__*/ __turbopack_context__.i("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/build/polyfills/process.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
// Live components (Phase 7): an EventSource on /api/stream drives the ticker
// and the live alert feed; polling /api/quotes is the fallback when SSE is
// unavailable. SnapshotRefresher re-renders the server page on an interval.
var __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/compiled/react/index.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/navigation.js [app-client] (ecmascript)");
;
var _s = __turbopack_context__.k.signature(), _s1 = __turbopack_context__.k.signature(), _s2 = __turbopack_context__.k.signature(), _s3 = __turbopack_context__.k.signature(), _s4 = __turbopack_context__.k.signature();
"use client";
;
;
const API = __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$build$2f$polyfills$2f$process$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["default"].env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
/* ---------------- shared SSE hook ---------------- */ function useStream(onQuote, onAlert) {
    _s();
    const [status, setStatus] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])("connecting");
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useEffect"])({
        "useStream.useEffect": ()=>{
            let es, pollTimer, dead = false;
            const startPolling = {
                "useStream.useEffect.startPolling": ()=>{
                    setStatus("polling");
                    const poll = {
                        "useStream.useEffect.startPolling.poll": async ()=>{
                            try {
                                const r = await fetch(`${API}/api/quotes`);
                                onQuote?.(await r.json());
                                setStatus("polling");
                            } catch  {
                                setStatus("offline");
                            }
                        }
                    }["useStream.useEffect.startPolling.poll"];
                    poll();
                    pollTimer = setInterval(poll, 20000);
                }
            }["useStream.useEffect.startPolling"];
            try {
                es = new EventSource(`${API}/api/stream`);
                es.addEventListener("hello", {
                    "useStream.useEffect": ()=>setStatus("live")
                }["useStream.useEffect"]);
                es.addEventListener("quote", {
                    "useStream.useEffect": (e)=>onQuote?.(JSON.parse(e.data))
                }["useStream.useEffect"]);
                es.addEventListener("alert", {
                    "useStream.useEffect": (e)=>onAlert?.(JSON.parse(e.data))
                }["useStream.useEffect"]);
                es.onerror = ({
                    "useStream.useEffect": ()=>{
                        if (dead) return;
                        setStatus("reconnecting");
                        // EventSource retries on its own; fall back to polling if it never lands
                        setTimeout({
                            "useStream.useEffect": ()=>{
                                if (!dead && es.readyState === EventSource.CLOSED) {
                                    es.close();
                                    startPolling();
                                }
                            }
                        }["useStream.useEffect"], 8000);
                    }
                })["useStream.useEffect"];
            } catch  {
                startPolling();
            }
            return ({
                "useStream.useEffect": ()=>{
                    dead = true;
                    es?.close();
                    clearInterval(pollTimer);
                }
            })["useStream.useEffect"];
        // eslint-disable-next-line react-hooks/exhaustive-deps
        }
    }["useStream.useEffect"], []);
    return status;
}
_s(useStream, "m77GlYSZ/kBaV+nYn7WleUGCczU=");
function LiveTicker() {
    _s1();
    const [quotes, setQuotes] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])({});
    const status = useStream({
        "LiveTicker.useStream[status]": (payload)=>{
            setQuotes({
                "LiveTicker.useStream[status]": (q)=>({
                        ...q,
                        ...payload.quotes
                    })
            }["LiveTicker.useStream[status]"]);
        }
    }["LiveTicker.useStream[status]"]);
    const syms = Object.keys(quotes);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "ticker",
        "aria-label": "Live quotes",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                className: `livedot ${status}`,
                title: status
            }, void 0, false, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                lineNumber: 69,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                className: "eyebrow",
                children: status
            }, void 0, false, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                lineNumber: 70,
                columnNumber: 7
            }, this),
            syms.length === 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                className: "empty",
                children: "waiting for quotes…"
            }, void 0, false, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                lineNumber: 71,
                columnNumber: 29
            }, this),
            syms.map((s)=>{
                const q = quotes[s];
                const up = q.change_pct >= 0;
                return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                    className: "tick num",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                            children: s
                        }, void 0, false, {
                            fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                            lineNumber: 77,
                            columnNumber: 13
                        }, this),
                        " ",
                        q.spot.toFixed(2),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("i", {
                            style: {
                                color: up ? "var(--bull)" : "var(--bear)"
                            },
                            children: [
                                up ? "+" : "",
                                q.change_pct.toFixed(2),
                                "%"
                            ]
                        }, void 0, true, {
                            fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                            lineNumber: 78,
                            columnNumber: 13
                        }, this)
                    ]
                }, s, true, {
                    fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                    lineNumber: 76,
                    columnNumber: 11
                }, this);
            })
        ]
    }, void 0, true, {
        fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
        lineNumber: 68,
        columnNumber: 5
    }, this);
}
_s1(LiveTicker, "BYndXr3VcTqO7YQhqJ3ZnyZ8e2g=", false, function() {
    return [
        useStream
    ];
});
_c = LiveTicker;
function LiveFeed({ initial }) {
    _s2();
    const [events, setEvents] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(initial?.events || []);
    const [liveCount, setLiveCount] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(0);
    useStream(null, {
        "LiveFeed.useStream": (ev)=>{
            setEvents({
                "LiveFeed.useStream": (prev)=>[
                        ...prev,
                        {
                            ...ev,
                            live: true
                        }
                    ]
            }["LiveFeed.useStream"]);
            setLiveCount({
                "LiveFeed.useStream": (n)=>n + 1
            }["LiveFeed.useStream"]);
        }
    }["LiveFeed.useStream"]);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
        className: "card",
        style: {
            marginTop: 18
        },
        "aria-label": "Alert feed",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                children: [
                    "Alert feed",
                    " ",
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: "num",
                        children: [
                            liveCount > 0 ? `${liveCount} live · ` : "",
                            initial?.label || ""
                        ]
                    }, void 0, true, {
                        fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                        lineNumber: 101,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                lineNumber: 99,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "feed",
                children: events.map((e, i)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: `fevent${e.live ? " liverow" : ""}`,
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "t num",
                                children: (e.bar_time || "").slice(0, 10)
                            }, void 0, false, {
                                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                                lineNumber: 108,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "num",
                                children: e.symbol
                            }, void 0, false, {
                                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                                lineNumber: 109,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    className: `badge ${e.to_state}`,
                                    children: (e.to_state || "").replaceAll("_", " ")
                                }, void 0, false, {
                                    fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                                    lineNumber: 110,
                                    columnNumber: 19
                                }, this)
                            }, void 0, false, {
                                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                                lineNumber: 110,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "why",
                                children: e.reason
                            }, void 0, false, {
                                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                                lineNumber: 111,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "px num",
                                children: e.price == null ? "—" : Number(e.price).toFixed(2)
                            }, void 0, false, {
                                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                                lineNumber: 112,
                                columnNumber: 13
                            }, this)
                        ]
                    }, i, true, {
                        fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                        lineNumber: 107,
                        columnNumber: 11
                    }, this))
            }, void 0, false, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                lineNumber: 105,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
        lineNumber: 98,
        columnNumber: 5
    }, this);
}
_s2(LiveFeed, "WB6aSPbGwfWpF2BOkMd0yzKadp8=", false, function() {
    return [
        useStream
    ];
});
_c1 = LiveFeed;
function ArmButton() {
    _s3();
    const [state, setState] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])({
        phase: "idle"
    });
    async function arm() {
        setState({
            phase: "arming"
        });
        try {
            const r = await fetch(`${API}/api/alerts/arm`, {
                method: "POST"
            });
            const data = await r.json();
            setState({
                phase: "armed",
                n: data.armed
            });
        } catch  {
            setState({
                phase: "error"
            });
        }
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "armrow",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                className: "armbtn",
                onClick: arm,
                disabled: state.phase === "arming",
                children: state.phase === "arming" ? "Arming…" : "Arm game plan"
            }, void 0, false, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                lineNumber: 136,
                columnNumber: 7
            }, this),
            state.phase === "armed" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                className: "state good",
                children: [
                    state.n,
                    " setup",
                    state.n === 1 ? "" : "s",
                    " armed — alerts will stream here"
                ]
            }, void 0, true, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                lineNumber: 140,
                columnNumber: 9
            }, this),
            state.phase === "error" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                className: "state bad",
                children: "API unreachable"
            }, void 0, false, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                lineNumber: 142,
                columnNumber: 35
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
        lineNumber: 135,
        columnNumber: 5
    }, this);
}
_s3(ArmButton, "udDURZxFbYBHiu8W0vp8t+bcgGo=");
_c2 = ArmButton;
function SnapshotRefresher({ intervalMs = 120000 }) {
    _s4();
    const router = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useRouter"])();
    const [last, setLast] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(null);
    const busy = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useRef"])(false);
    async function refresh(force) {
        if (busy.current) return;
        busy.current = true;
        try {
            if (force) await fetch(`${API}/api/snapshot?refresh=1`);
            router.refresh();
            setLast(new Date());
        } finally{
            busy.current = false;
        }
    }
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useEffect"])({
        "SnapshotRefresher.useEffect": ()=>{
            const t = setInterval({
                "SnapshotRefresher.useEffect.t": ()=>refresh(false)
            }["SnapshotRefresher.useEffect.t"], intervalMs);
            return ({
                "SnapshotRefresher.useEffect": ()=>clearInterval(t)
            })["SnapshotRefresher.useEffect"];
        // eslint-disable-next-line react-hooks/exhaustive-deps
        }
    }["SnapshotRefresher.useEffect"], [
        intervalMs
    ]);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
        className: "refresher",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                className: "chip",
                type: "button",
                onClick: ()=>refresh(true),
                children: "↻ refresh"
            }, void 0, false, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                lineNumber: 171,
                columnNumber: 7
            }, this),
            last && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                className: "num",
                style: {
                    fontSize: 11,
                    color: "var(--faint)"
                },
                children: last.toLocaleTimeString()
            }, void 0, false, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                lineNumber: 172,
                columnNumber: 16
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
        lineNumber: 170,
        columnNumber: 5
    }, this);
}
_s4(SnapshotRefresher, "cZbQQNwcVU4+KB0aFrsL4jcepiU=", false, function() {
    return [
        __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useRouter"]
    ];
});
_c3 = SnapshotRefresher;
var _c, _c1, _c2, _c3;
__turbopack_context__.k.register(_c, "LiveTicker");
__turbopack_context__.k.register(_c1, "LiveFeed");
__turbopack_context__.k.register(_c2, "ArmButton");
__turbopack_context__.k.register(_c3, "SnapshotRefresher");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/compiled/react/cjs/react-jsx-dev-runtime.development.js [app-client] (ecmascript)", ((__turbopack_context__, module, exports) => {
"use strict";

var __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$build$2f$polyfills$2f$process$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = /*#__PURE__*/ __turbopack_context__.i("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/build/polyfills/process.js [app-client] (ecmascript)");
/**
 * @license React
 * react-jsx-dev-runtime.development.js
 *
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */ "use strict";
"production" !== ("TURBOPACK compile-time value", "development") && function() {
    function getComponentNameFromType(type) {
        if (null == type) return null;
        if ("function" === typeof type) return type.$$typeof === REACT_CLIENT_REFERENCE ? null : type.displayName || type.name || null;
        if ("string" === typeof type) return type;
        switch(type){
            case REACT_FRAGMENT_TYPE:
                return "Fragment";
            case REACT_PROFILER_TYPE:
                return "Profiler";
            case REACT_STRICT_MODE_TYPE:
                return "StrictMode";
            case REACT_SUSPENSE_TYPE:
                return "Suspense";
            case REACT_SUSPENSE_LIST_TYPE:
                return "SuspenseList";
            case REACT_ACTIVITY_TYPE:
                return "Activity";
            case REACT_VIEW_TRANSITION_TYPE:
                return "ViewTransition";
        }
        if ("object" === typeof type) switch("number" === typeof type.tag && console.error("Received an unexpected object in getComponentNameFromType(). This is likely a bug in React. Please file an issue."), type.$$typeof){
            case REACT_PORTAL_TYPE:
                return "Portal";
            case REACT_CONTEXT_TYPE:
                return type.displayName || "Context";
            case REACT_CONSUMER_TYPE:
                return (type._context.displayName || "Context") + ".Consumer";
            case REACT_FORWARD_REF_TYPE:
                var innerType = type.render;
                type = type.displayName;
                type || (type = innerType.displayName || innerType.name || "", type = "" !== type ? "ForwardRef(" + type + ")" : "ForwardRef");
                return type;
            case REACT_MEMO_TYPE:
                return innerType = type.displayName || null, null !== innerType ? innerType : getComponentNameFromType(type.type) || "Memo";
            case REACT_LAZY_TYPE:
                innerType = type._payload;
                type = type._init;
                try {
                    return getComponentNameFromType(type(innerType));
                } catch (x) {}
        }
        return null;
    }
    function testStringCoercion(value) {
        return "" + value;
    }
    function checkKeyStringCoercion(value) {
        try {
            testStringCoercion(value);
            var JSCompiler_inline_result = !1;
        } catch (e) {
            JSCompiler_inline_result = !0;
        }
        if (JSCompiler_inline_result) {
            JSCompiler_inline_result = console;
            var JSCompiler_temp_const = JSCompiler_inline_result.error;
            var JSCompiler_inline_result$jscomp$0 = "function" === typeof Symbol && Symbol.toStringTag && value[Symbol.toStringTag] || value.constructor.name || "Object";
            JSCompiler_temp_const.call(JSCompiler_inline_result, "The provided key is an unsupported type %s. This value must be coerced to a string before using it here.", JSCompiler_inline_result$jscomp$0);
            return testStringCoercion(value);
        }
    }
    function getTaskName(type) {
        if (type === REACT_FRAGMENT_TYPE) return "<>";
        if ("object" === typeof type && null !== type && type.$$typeof === REACT_LAZY_TYPE) return "<...>";
        try {
            var name = getComponentNameFromType(type);
            return name ? "<" + name + ">" : "<...>";
        } catch (x) {
            return "<...>";
        }
    }
    function getOwner() {
        var dispatcher = ReactSharedInternals.A;
        return null === dispatcher ? null : dispatcher.getOwner();
    }
    function UnknownOwner() {
        return Error("react-stack-top-frame");
    }
    function hasValidKey(config) {
        if (hasOwnProperty.call(config, "key")) {
            var getter = Object.getOwnPropertyDescriptor(config, "key").get;
            if (getter && getter.isReactWarning) return !1;
        }
        return void 0 !== config.key;
    }
    function defineKeyPropWarningGetter(props, displayName) {
        function warnAboutAccessingKey() {
            specialPropKeyWarningShown || (specialPropKeyWarningShown = !0, console.error("%s: `key` is not a prop. Trying to access it will result in `undefined` being returned. If you need to access the same value within the child component, you should pass it as a different prop. (https://react.dev/link/special-props)", displayName));
        }
        warnAboutAccessingKey.isReactWarning = !0;
        Object.defineProperty(props, "key", {
            get: warnAboutAccessingKey,
            configurable: !0
        });
    }
    function elementRefGetterWithDeprecationWarning() {
        var componentName = getComponentNameFromType(this.type);
        didWarnAboutElementRef[componentName] || (didWarnAboutElementRef[componentName] = !0, console.error("Accessing element.ref was removed in React 19. ref is now a regular prop. It will be removed from the JSX Element type in a future release."));
        componentName = this.props.ref;
        return void 0 !== componentName ? componentName : null;
    }
    function ReactElement(type, key, props, owner, debugStack, debugTask) {
        var refProp = props.ref;
        type = {
            $$typeof: REACT_ELEMENT_TYPE,
            type: type,
            key: key,
            props: props,
            _owner: owner
        };
        null !== (void 0 !== refProp ? refProp : null) ? Object.defineProperty(type, "ref", {
            enumerable: !1,
            get: elementRefGetterWithDeprecationWarning
        }) : Object.defineProperty(type, "ref", {
            enumerable: !1,
            value: null
        });
        type._store = {};
        Object.defineProperty(type._store, "validated", {
            configurable: !1,
            enumerable: !1,
            writable: !0,
            value: 0
        });
        Object.defineProperty(type, "_debugInfo", {
            configurable: !1,
            enumerable: !1,
            writable: !0,
            value: null
        });
        Object.defineProperty(type, "_debugStack", {
            configurable: !1,
            enumerable: !1,
            writable: !0,
            value: debugStack
        });
        Object.defineProperty(type, "_debugTask", {
            configurable: !1,
            enumerable: !1,
            writable: !0,
            value: debugTask
        });
        Object.freeze && (Object.freeze(type.props), Object.freeze(type));
        return type;
    }
    function jsxDEVImpl(type, config, maybeKey, isStaticChildren, debugStack, debugTask) {
        var children = config.children;
        if (void 0 !== children) if (isStaticChildren) if (isArrayImpl(children)) {
            for(isStaticChildren = 0; isStaticChildren < children.length; isStaticChildren++)validateChildKeys(children[isStaticChildren]);
            Object.freeze && Object.freeze(children);
        } else console.error("React.jsx: Static children should always be an array. You are likely explicitly calling React.jsxs or React.jsxDEV. Use the Babel transform instead.");
        else validateChildKeys(children);
        if (hasOwnProperty.call(config, "key")) {
            children = getComponentNameFromType(type);
            var keys = Object.keys(config).filter(function(k) {
                return "key" !== k;
            });
            isStaticChildren = 0 < keys.length ? "{key: someKey, " + keys.join(": ..., ") + ": ...}" : "{key: someKey}";
            didWarnAboutKeySpread[children + isStaticChildren] || (keys = 0 < keys.length ? "{" + keys.join(": ..., ") + ": ...}" : "{}", console.error('A props object containing a "key" prop is being spread into JSX:\n  let props = %s;\n  <%s {...props} />\nReact keys must be passed directly to JSX without using spread:\n  let props = %s;\n  <%s key={someKey} {...props} />', isStaticChildren, children, keys, children), didWarnAboutKeySpread[children + isStaticChildren] = !0);
        }
        children = null;
        void 0 !== maybeKey && (checkKeyStringCoercion(maybeKey), children = "" + maybeKey);
        hasValidKey(config) && (checkKeyStringCoercion(config.key), children = "" + config.key);
        if ("key" in config) {
            maybeKey = {};
            for(var propName in config)"key" !== propName && (maybeKey[propName] = config[propName]);
        } else maybeKey = config;
        children && defineKeyPropWarningGetter(maybeKey, "function" === typeof type ? type.displayName || type.name || "Unknown" : type);
        return ReactElement(type, children, maybeKey, getOwner(), debugStack, debugTask);
    }
    function validateChildKeys(node) {
        isValidElement(node) ? node._store && (node._store.validated = 1) : "object" === typeof node && null !== node && node.$$typeof === REACT_LAZY_TYPE && ("fulfilled" === node._payload.status ? isValidElement(node._payload.value) && node._payload.value._store && (node._payload.value._store.validated = 1) : node._store && (node._store.validated = 1));
    }
    function isValidElement(object) {
        return "object" === typeof object && null !== object && object.$$typeof === REACT_ELEMENT_TYPE;
    }
    var React = __turbopack_context__.r("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/compiled/react/index.js [app-client] (ecmascript)"), REACT_ELEMENT_TYPE = Symbol.for("react.transitional.element"), REACT_PORTAL_TYPE = Symbol.for("react.portal"), REACT_FRAGMENT_TYPE = Symbol.for("react.fragment"), REACT_STRICT_MODE_TYPE = Symbol.for("react.strict_mode"), REACT_PROFILER_TYPE = Symbol.for("react.profiler"), REACT_CONSUMER_TYPE = Symbol.for("react.consumer"), REACT_CONTEXT_TYPE = Symbol.for("react.context"), REACT_FORWARD_REF_TYPE = Symbol.for("react.forward_ref"), REACT_SUSPENSE_TYPE = Symbol.for("react.suspense"), REACT_SUSPENSE_LIST_TYPE = Symbol.for("react.suspense_list"), REACT_MEMO_TYPE = Symbol.for("react.memo"), REACT_LAZY_TYPE = Symbol.for("react.lazy"), REACT_ACTIVITY_TYPE = Symbol.for("react.activity"), REACT_VIEW_TRANSITION_TYPE = Symbol.for("react.view_transition"), REACT_CLIENT_REFERENCE = Symbol.for("react.client.reference"), ReactSharedInternals = React.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE, hasOwnProperty = Object.prototype.hasOwnProperty, isArrayImpl = Array.isArray, createTask = console.createTask ? console.createTask : function() {
        return null;
    };
    React = {
        react_stack_bottom_frame: function(callStackForError) {
            return callStackForError();
        }
    };
    var specialPropKeyWarningShown;
    var didWarnAboutElementRef = {};
    var unknownOwnerDebugStack = React.react_stack_bottom_frame.bind(React, UnknownOwner)();
    var unknownOwnerDebugTask = createTask(getTaskName(UnknownOwner));
    var didWarnAboutKeySpread = {};
    exports.Fragment = REACT_FRAGMENT_TYPE;
    exports.jsxDEV = function(type, config, maybeKey, isStaticChildren) {
        var trackActualOwner = 1e4 > ReactSharedInternals.recentlyCreatedOwnerStacks++;
        if (trackActualOwner) {
            var previousStackTraceLimit = Error.stackTraceLimit;
            Error.stackTraceLimit = 10;
            var debugStackDEV = Error("react-stack-top-frame");
            Error.stackTraceLimit = previousStackTraceLimit;
        } else debugStackDEV = unknownOwnerDebugStack;
        return jsxDEVImpl(type, config, maybeKey, isStaticChildren, debugStackDEV, trackActualOwner ? createTask(getTaskName(type)) : unknownOwnerDebugTask);
    };
}();
}),
"[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)", ((__turbopack_context__, module, exports) => {
"use strict";

var __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$build$2f$polyfills$2f$process$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = /*#__PURE__*/ __turbopack_context__.i("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/build/polyfills/process.js [app-client] (ecmascript)");
'use strict';
if ("TURBOPACK compile-time falsy", 0) //TURBOPACK unreachable
;
else {
    module.exports = __turbopack_context__.r("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/compiled/react/cjs/react-jsx-dev-runtime.development.js [app-client] (ecmascript)");
}
}),
"[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/navigation.js [app-client] (ecmascript)", ((__turbopack_context__, module, exports) => {

module.exports = __turbopack_context__.r("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/client/components/navigation.js [app-client] (ecmascript)");
}),
]);

//# sourceMappingURL=source_repos_AI%20Trading%20Model%20-%20Claude_apps_web_1ug8ttg._.js.map