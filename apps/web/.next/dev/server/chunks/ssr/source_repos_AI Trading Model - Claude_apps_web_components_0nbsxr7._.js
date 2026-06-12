module.exports = [
"[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "default",
    ()=>Chat
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
"use client";
;
;
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
function Chat() {
    const [messages, setMessages] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])([]);
    const [input, setInput] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [busy, setBusy] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const boxRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(null);
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
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
        className: "card",
        style: {
            marginTop: 18
        },
        "aria-label": "Chat",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                children: "Ask Confluence"
            }, void 0, false, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                lineNumber: 49,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                ref: boxRef,
                className: "chatbox",
                children: [
                    messages.length === 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "empty",
                        children: [
                            "Ask about the regime, levels, sectors, setups, extension, gamma…",
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "sugg",
                                children: suggestions.map((s)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
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
                    messages.map((m, i)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: `msg ${m.role}`,
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    className: "who",
                                    children: m.role === "user" ? "you" : `confluence${m.mode === "deterministic" ? " · deterministic" : ""}`
                                }, void 0, false, {
                                    fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                                    lineNumber: 64,
                                    columnNumber: 13
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
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
                    busy && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "msg assistant",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "who",
                                children: "confluence"
                            }, void 0, false, {
                                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                                lineNumber: 68,
                                columnNumber: 49
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
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
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("form", {
                className: "chatrow",
                onSubmit: send,
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                        value: input,
                        onChange: (e)=>setInput(e.target.value),
                        placeholder: "What level invalidates the NVDA trade?",
                        "aria-label": "Message"
                    }, void 0, false, {
                        fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Chat.jsx",
                        lineNumber: 71,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
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
}),
"[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
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
var __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
// Live components (Phase 7): an EventSource on /api/stream drives the ticker
// and the live alert feed; polling /api/quotes is the fallback when SSE is
// unavailable. SnapshotRefresher re-renders the server page on an interval.
var __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/source/repos/AI Trading Model - Claude/apps/web/node_modules/next/navigation.js [app-ssr] (ecmascript)");
"use client";
;
;
;
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
/* ---------------- shared SSE hook ---------------- */ function useStream(onQuote, onAlert) {
    const [status, setStatus] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("connecting");
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        let es, pollTimer, dead = false;
        const startPolling = ()=>{
            setStatus("polling");
            const poll = async ()=>{
                try {
                    const r = await fetch(`${API}/api/quotes`);
                    onQuote?.(await r.json());
                    setStatus("polling");
                } catch  {
                    setStatus("offline");
                }
            };
            poll();
            pollTimer = setInterval(poll, 20000);
        };
        try {
            es = new EventSource(`${API}/api/stream`);
            es.addEventListener("hello", ()=>setStatus("live"));
            es.addEventListener("quote", (e)=>onQuote?.(JSON.parse(e.data)));
            es.addEventListener("alert", (e)=>onAlert?.(JSON.parse(e.data)));
            es.onerror = ()=>{
                if (dead) return;
                setStatus("reconnecting");
                // EventSource retries on its own; fall back to polling if it never lands
                setTimeout(()=>{
                    if (!dead && es.readyState === EventSource.CLOSED) {
                        es.close();
                        startPolling();
                    }
                }, 8000);
            };
        } catch  {
            startPolling();
        }
        return ()=>{
            dead = true;
            es?.close();
            clearInterval(pollTimer);
        };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return status;
}
function LiveTicker() {
    const [quotes, setQuotes] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])({});
    const status = useStream((payload)=>{
        setQuotes((q)=>({
                ...q,
                ...payload.quotes
            }));
    });
    const syms = Object.keys(quotes);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "ticker",
        "aria-label": "Live quotes",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                className: `livedot ${status}`,
                title: status
            }, void 0, false, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                lineNumber: 69,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                className: "eyebrow",
                children: status
            }, void 0, false, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                lineNumber: 70,
                columnNumber: 7
            }, this),
            syms.length === 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
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
                return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                    className: "tick num",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                            children: s
                        }, void 0, false, {
                            fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                            lineNumber: 77,
                            columnNumber: 13
                        }, this),
                        " ",
                        q.spot.toFixed(2),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("i", {
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
function LiveFeed({ initial }) {
    const [events, setEvents] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(initial?.events || []);
    const [liveCount, setLiveCount] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(0);
    useStream(null, (ev)=>{
        setEvents((prev)=>[
                ...prev,
                {
                    ...ev,
                    live: true
                }
            ]);
        setLiveCount((n)=>n + 1);
    });
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("section", {
        className: "card",
        style: {
            marginTop: 18
        },
        "aria-label": "Alert feed",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                children: [
                    "Alert feed",
                    " ",
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
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
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "feed",
                children: events.map((e, i)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: `fevent${e.live ? " liverow" : ""}`,
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "t num",
                                children: (e.bar_time || "").slice(0, 10)
                            }, void 0, false, {
                                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                                lineNumber: 108,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "num",
                                children: e.symbol
                            }, void 0, false, {
                                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                                lineNumber: 109,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
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
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "why",
                                children: e.reason
                            }, void 0, false, {
                                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                                lineNumber: 111,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
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
function ArmButton() {
    const [state, setState] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])({
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
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "armrow",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                className: "armbtn",
                onClick: arm,
                disabled: state.phase === "arming",
                children: state.phase === "arming" ? "Arming…" : "Arm game plan"
            }, void 0, false, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                lineNumber: 136,
                columnNumber: 7
            }, this),
            state.phase === "armed" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
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
            state.phase === "error" && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
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
function SnapshotRefresher({ intervalMs = 120000 }) {
    const router = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRouter"])();
    const [last, setLast] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const busy = (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(false);
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
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        const t = setInterval(()=>refresh(false), intervalMs);
        return ()=>clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [
        intervalMs
    ]);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
        className: "refresher",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                className: "chip",
                type: "button",
                onClick: ()=>refresh(true),
                children: "↻ refresh"
            }, void 0, false, {
                fileName: "[project]/source/repos/AI Trading Model - Claude/apps/web/components/Live.jsx",
                lineNumber: 171,
                columnNumber: 7
            }, this),
            last && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$source$2f$repos$2f$AI__Trading__Model__$2d$__Claude$2f$apps$2f$web$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
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
}),
];

//# sourceMappingURL=source_repos_AI%20Trading%20Model%20-%20Claude_apps_web_components_0nbsxr7._.js.map