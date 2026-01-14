import React, { useState, useEffect, useRef } from 'react';
import { Agent, VALID_OWNER_NAMES } from './lib/agent';
import { Send, Database, Brain, Loader2, Settings, ThumbsUp, ThumbsDown, Trophy, User, Radio, Mic } from 'lucide-react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

type Message = { role: 'user' | 'assistant', content: string, data?: any[], sql?: string };

const MODELS = {
  primary: "Qwen2.5-1.5B-Instruct-q4f16_1-MLC",
  robust: "Phi-3.5-mini-instruct-q4f16_1-MLC",
};

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [agent, setAgent] = useState<Agent | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const [thoughts, setThoughts] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState(MODELS.primary);
  const [isInitializing, setIsInitializing] = useState(false);
  const [managerIdentity, setManagerIdentity] = useState<string | null>(() => localStorage.getItem('ff_manager_identity'));
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, thoughts]);

  const initAgent = async () => {
    setIsInitializing(true);
    const newAgent = new Agent((state) => {
      setStatus(state.status);
      setThoughts([...state.thoughts]); // Copy to trigger re-render
    });

    try {
      await newAgent.init(selectedModel);
      setAgent(newAgent);
    } catch (e) {
      console.error(e);
      alert("Failed to initialize agent. See console.");
    } finally {
      setIsInitializing(false);
    }
  };

  const selectManager = (name: string) => {
    localStorage.setItem('ff_manager_identity', name);
    setManagerIdentity(name);
  };

  const handleSwitchManager = () => {
    if (confirm("Switch manager identity? This will refresh the session.")) {
      localStorage.removeItem('ff_manager_identity');
      window.location.reload();
    }
  };

  const handleFeedback = async (value: number) => {
    if (!agent) return;
    await agent.scoreLastTrace(value);
    // Optionally show a "thank you" toast or disable buttons
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !agent || status !== 'idle') return;

    const userMsg: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setThoughts([]); // Clear previous thoughts

    try {
      // Filter history for context (last 10 messages)
      const history = messages.slice(-10).map(m => ({
        role: m.role,
        content: m.content
      }));

      // Add user message to history effectively
      // Actually the agent handles this but we pass history strictly as context

      const result = await agent.processQuery(userMsg.content, [...history, { role: 'user', content: userMsg.content }] as any);

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: result.answer,
        data: result.data,
        sql: result.sql
      }]);
    } catch (err) {
      console.error('Query processing error:', err);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: "I'm sorry, I encountered an error while processing your request."
      }]);
    }
  };

  if (!managerIdentity) {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center p-4">
        <div className="max-w-2xl w-full">
          <div className="text-center mb-12">
            <Trophy className="w-16 h-16 text-yellow-500 mx-auto mb-4" />
            <h1 className="text-4xl font-black uppercase tracking-tighter mb-2 italic">Sports Desk: Identity Check</h1>
            <p className="text-gray-400">Identify yourself, Commish. Who are you managing?</p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {VALID_OWNER_NAMES.map((name) => (
              <button
                key={name}
                onClick={() => selectManager(name)}
                className="bg-gray-900 border border-gray-800 hover:border-blue-500 hover:bg-gray-800 p-6 rounded-xl transition group text-center"
              >
                <div className="w-12 h-12 bg-gray-800 rounded-full flex items-center justify-center mx-auto mb-3 group-hover:bg-blue-600 transition">
                  <User className="w-6 h-6 text-gray-400 group-hover:text-white" />
                </div>
                <span className="font-bold text-lg">{name}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-gray-900 rounded-2xl p-8 shadow-2xl border border-gray-800">
          <div className="flex justify-center mb-6">
            <div className="p-4 bg-blue-600/20 rounded-2xl">
              <Brain className="w-12 h-12 text-blue-500" />
            </div>
          </div>
          <h1 className="text-2xl font-bold text-center mb-1">Welcome back, {managerIdentity}</h1>
          <p className="text-gray-400 text-center mb-8 text-sm">
            Initializing Sports Desk AI Control Room.
          </p>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-widest mb-1 ml-1">Transmission Model</label>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full bg-gray-950 border border-gray-800 rounded-xl p-4 text-white focus:ring-2 focus:ring-blue-500 outline-none appearance-none"
              >
                <option value={MODELS.primary}>Qwen 2.5 (1.5B) - Fast</option>
                <option value={MODELS.robust}>Phi 3.5 (3.8B) - Robust</option>
              </select>
            </div>

            <button
              onClick={initAgent}
              disabled={isInitializing}
              className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-800 text-white font-black py-4 px-4 rounded-xl transition flex items-center justify-center gap-3 uppercase tracking-tighter"
            >
              {isInitializing ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Calibrating...
                </>
              ) : (
                "Go Live"
              )}
            </button>

            {isInitializing && (
              <div className="mt-4 p-4 bg-black rounded-xl border border-gray-800 text-xs font-mono text-emerald-400 h-32 overflow-y-auto scrollbar-hide">
                {thoughts.map((t, i) => <div key={i} className="mb-1">{`> ${t}`}</div>)}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-gray-950 text-white flex flex-col overflow-hidden font-sans selection:bg-blue-500/30">
      {/* Header */}
      <header className="bg-gray-900/80 backdrop-blur-md border-b border-gray-800 p-4 flex items-center justify-between shadow-2xl relative z-20">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-600 rounded-lg shadow-lg shadow-blue-900/20">
            <Radio className="w-5 h-5 text-white animate-pulse" />
          </div>
          <div>
            <h1 className="font-black text-xl italic tracking-tighter uppercase leading-none">Sports Desk</h1>
            <div className="text-[10px] text-blue-400 font-bold tracking-[0.2em] uppercase mt-0.5">Live Logic Transmission</div>
          </div>
        </div>
        <div className="flex items-center gap-6">
          <div className="hidden lg:flex flex-col items-end">
            <span className="text-[10px] text-gray-500 font-bold uppercase tracking-widest">Active Manager</span>
            <span className="text-sm font-black text-white italic">{managerIdentity}</span>
          </div>
          <div className="h-8 w-px bg-gray-800 hidden lg:block" />
          <div className="flex items-center gap-4 text-sm text-gray-400">
            <span className={cn("flex items-center gap-2 px-3 py-1 rounded-full bg-gray-950 border border-gray-800", status !== 'idle' ? "text-yellow-400 border-yellow-900/30" : "text-emerald-400 border-emerald-900/30")}>
              <span className="w-2 h-2 rounded-full bg-current animate-pulse status-pulse" />
              <span data-testid="status-indicator" className="uppercase font-black tracking-widest text-[10px]">{status === 'idle' ? 'Ready' : status}</span>
            </span>
            <button
              onClick={handleSwitchManager}
              className="p-2 hover:bg-gray-800 rounded-lg transition-colors group"
              title="Identity Settings"
            >
              <Settings className="w-5 h-5 group-hover:rotate-90 transition-transform duration-500" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Live Logic Feed (Side Panel) */}
        <aside className="w-80 bg-gray-900/30 border-r border-gray-800 flex flex-col hidden xl:flex">
          <div className="p-4 border-b border-gray-800 bg-gray-900/50 flex items-center gap-2">
            <Mic className="w-4 h-4 text-blue-500" />
            <span className="font-black italic uppercase tracking-tighter text-sm">Live Logic Feed</span>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-hide">
            {thoughts.length === 0 && <div className="text-gray-700 font-mono text-xs italic">Waiting for transmission...</div>}
            {thoughts.map((t, i) => (
              <div key={i} className="animate-in slide-in-from-left-2 duration-300">
                <div className="flex gap-2">
                  <span className="text-blue-600 font-mono text-[10px] mt-0.5 mt-1">[{new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}]</span>
                  <p className="text-xs font-mono text-gray-400 leading-relaxed border-l border-gray-800 pl-3">{t}</p>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
          <div className="p-4 bg-gray-900/50 border-t border-gray-800">
            <div className="flex items-center justify-between text-[10px] font-bold text-gray-500 uppercase tracking-widest">
              <span>Syncing with Local LLM</span>
              <div className="flex gap-1">
                <div className="w-1 h-3 bg-blue-600 animate-pulse" />
                <div className="w-1 h-3 bg-blue-600 animate-pulse [animation-delay:200ms]" />
                <div className="w-1 h-3 bg-blue-600 animate-pulse [animation-delay:400ms]" />
              </div>
            </div>
          </div>
        </aside>

        {/* Chat Area */}
        <div className="flex-1 flex flex-col relative bg-[linear-gradient(to_bottom,rgba(10,14,26,0.8),rgba(10,14,26,1)),url('https://www.transparenttextures.com/patterns/carbon-fibre.png')]">
          <div className="flex-1 overflow-y-auto p-6 space-y-8 scrollbar-hide">
            <div className="max-w-4xl mx-auto space-y-8 pb-12">
              {messages.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full py-20 text-center opacity-50">
                  <Trophy className="w-16 h-16 text-yellow-600 mb-6" />
                  <h2 className="text-2xl font-black italic uppercase tracking-tighter">Sports Desk is Open</h2>
                  <p className="max-w-xs text-sm text-gray-400 mt-2 font-medium">Ask about stats, match history, or league lore.</p>
                </div>
              )}

              {messages.map((m, i) => (
                <div key={i} className={cn("flex gap-6 animate-in fade-in slide-in-from-bottom-4 duration-500", m.role === 'user' ? "flex-row-reverse" : "")} data-testid={`message-${m.role}`}>
                  <div className={cn(
                    "w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 border-2 shadow-xl",
                    m.role === 'user' ? "bg-blue-600 border-blue-400 rotate-3" : "bg-gray-900 border-gray-700 -rotate-3"
                  )}>
                    {m.role === 'user' ? <User className="w-6 h-6" /> : <Mic className="w-6 h-6 text-blue-500" />}
                  </div>
                  <div className={cn(
                    "rounded-3xl p-6 max-w-[85%] relative",
                    m.role === 'user' ? "bg-blue-600 text-white rounded-tr-none shadow-blue-900/20" : "bg-gray-900/80 backdrop-blur-sm border border-gray-800 text-gray-100 rounded-tl-none shadow-black/40"
                  )} data-testid={`message-content-${m.role}`}>
                    {/* Breaking News Badge */}
                    {m.role === 'assistant' && m.content.length > 200 && (
                      <div className="absolute -top-3 left-6 bg-yellow-500 text-black text-[10px] font-black uppercase tracking-tighter px-3 py-1 rounded-full italic shadow-lg flex items-center gap-1">
                        <Radio className="w-3 h-3 animate-pulse" /> Breaking News
                      </div>
                    )}

                    <p className="text-lg leading-relaxed font-medium selection:bg-yellow-500 selection:text-black">{m.content}</p>

                    {m.sql && (
                      <div className="mt-6 bg-black/50 rounded-2xl p-4 border border-gray-800 font-mono text-sm overflow-x-auto">
                        <div className="flex items-center gap-2 mb-2">
                          <Database className="w-4 h-4 text-emerald-500" />
                          <span className="text-gray-500 text-xs font-bold uppercase tracking-widest">Live SQL Query Execution</span>
                        </div>
                        <code className="text-emerald-400">{m.sql}</code>
                      </div>
                    )}

                    {m.data && m.data.length > 0 && (
                      <div className="mt-6 overflow-hidden rounded-2xl border border-gray-800 shadow-2xl">
                        <div className="bg-gray-950 px-4 py-2 border-b border-gray-800 flex items-center justify-between">
                          <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Broadcast Data Result</span>
                          <span className="text-[10px] font-bold text-blue-500 underline uppercase tracking-tighter cursor-pointer">Export CSV</span>
                        </div>
                        <div className="overflow-x-auto">
                          <table className="min-w-full text-xs text-left">
                            <thead className="bg-gray-950 uppercase font-black text-gray-400 tracking-tighter border-b border-gray-800">
                              <tr>
                                {Object.keys(m.data[0]).map((k) => (
                                  <th key={k} className="px-5 py-3">{k}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-800/50">
                              {m.data.slice(0, 5).map((row: any, idx: number) => (
                                <tr key={idx} className="hover:bg-blue-600/5 transition-colors">
                                  {Object.values(row).map((v: any, vIdx) => (
                                    <td key={vIdx} className="px-5 py-3 font-medium text-gray-300">{String(v)}</td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {m.data.length > 5 && (
                          <div className="bg-gray-950/50 p-3 text-center text-[10px] font-bold text-gray-600 border-t border-gray-800 uppercase tracking-widest">
                            + {m.data.length - 5} More Rows in Archive
                          </div>
                        )}
                      </div>
                    )}

                    {m.role === 'assistant' && i === messages.length - 1 && (
                      <div className="mt-6 flex items-center justify-end gap-4 border-t border-gray-800/50 pt-4">
                        <span className="text-[10px] font-black text-gray-600 uppercase tracking-widest">Reception Check?</span>
                        <div className="flex gap-2">
                          <button onClick={() => handleFeedback(1)} className="p-2 hover:bg-emerald-500/10 hover:text-emerald-400 rounded-lg transition-all group"><ThumbsUp className="w-5 h-5 group-hover:scale-110 transition-transform" /></button>
                          <button onClick={() => handleFeedback(-1)} className="p-2 hover:bg-red-500/10 hover:text-red-400 rounded-lg transition-all group"><ThumbsDown className="w-5 h-5 group-hover:scale-110 transition-transform" /></button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input Area */}
          <div className="p-6 bg-gray-900/50 backdrop-blur-xl border-t border-gray-800 relative z-10">
            <form onSubmit={handleSubmit} className="max-w-4xl mx-auto relative group">
              <div className="absolute -inset-1 bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl blur opacity-20 group-focus-within:opacity-40 transition duration-500" />
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Submit query to Sports Desk logic room..."
                disabled={status !== 'idle'}
                className="relative w-full bg-gray-950 border border-gray-800 rounded-2xl py-5 pl-6 pr-16 text-white text-lg placeholder-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none disabled:opacity-50 transition-all font-medium italic tracking-tight"
                data-testid="chat-input"
              />
              <button
                type="submit"
                disabled={!input.trim() || status !== 'idle'}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-3 bg-blue-600 rounded-xl text-white hover:bg-blue-500 disabled:bg-gray-800 disabled:text-gray-600 transition-all shadow-lg active:scale-95"
              >
                <Send className="w-6 h-6" />
              </button>
            </form>
          </div>

          {/* Real-Time Ticker */}
          <div className="h-10 bg-blue-900/20 border-t border-blue-900/30 overflow-hidden flex items-center">
            <div className="bg-blue-600 h-full px-4 flex items-center z-10 shadow-xl">
              <span className="font-black italic uppercase tracking-tighter text-[10px] text-white whitespace-nowrap">Live Status</span>
            </div>
            <div className="flex-1 relative overflow-hidden h-full flex items-center">
              <div className="whitespace-nowrap flex gap-12 animate-marquee items-center">
                <span className="text-yellow-500 font-bold uppercase tracking-widest text-[10px] flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-yellow-500 rounded-full animate-pulse" />
                  {getTickerText(status)}
                </span>
                <span className="text-blue-400 font-bold uppercase tracking-widest text-[10px]">Transmission secured via Local Browser LLM</span>
                <span className="text-gray-500 font-bold uppercase tracking-widest text-[10px]">Manager Identity Validated: {managerIdentity}</span>
                <span className="text-emerald-500 font-bold uppercase tracking-widest text-[10px]">Database Connection: Optimized SQLite Wide-Table</span>
                {/* Repeat for continuous look */}
                <span className="text-yellow-500 font-bold uppercase tracking-widest text-[10px] flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-yellow-500 rounded-full animate-pulse" />
                  {getTickerText(status)}
                </span>
                <span className="text-blue-400 font-bold uppercase tracking-widest text-[10px]">Transmission secured via Local Browser LLM</span>
              </div>
            </div>
            <div className="bg-gray-900 h-full px-4 flex items-center border-l border-gray-800">
              <span className="font-mono text-[10px] text-gray-400 uppercase tracking-tighter">{new Date().toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function getTickerText(status: string) {
  switch (status) {
    case 'thinking': return "Analyzing Query Context and Historical Patterns...";
    case 'querying': return "Scanning High-Speed SQL Database for Relevant Manager Data...";
    case 'executing': return "LIVE: Running SQL Transformation on Local SQLite Engine...";
    case 'reflecting': return "Validating Results and Optimizing Narrative Response...";
    case 'answering': return "Transmitting Live Broadcast Message to Desk Area...";
    case 'idle': return "Standing By: Ready for Statistical Analysis or League Lore Inquiries...";
    default: return "System Online: Initializing Web-LLM Worker Protocols...";
  }
}

export default App;
