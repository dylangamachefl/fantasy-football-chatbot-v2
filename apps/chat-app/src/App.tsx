import React, { useState, useEffect, useRef } from 'react';
import { Agent } from './lib/agent';
import { Send, Database, Brain, Loader2, Settings, ThumbsUp, ThumbsDown } from 'lucide-react';
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

  if (!agent) {
    return (
      <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-gray-800 rounded-xl p-8 shadow-2xl border border-gray-700">
          <div className="flex justify-center mb-6">
            <Brain className="w-16 h-16 text-blue-500" />
          </div>
          <h1 className="text-2xl font-bold text-center mb-2">Local SQL Agent</h1>
          <p className="text-gray-400 text-center mb-8">
            Zero-server RAG system running entirely in your browser.
          </p>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">Select Model</label>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg p-3 text-white focus:ring-2 focus:ring-blue-500 outline-none"
              >
                <option value={MODELS.primary}>Qwen 2.5 (1.5B) - Fast</option>
                <option value={MODELS.robust}>Phi 3.5 (3.8B) - Robust</option>
              </select>
            </div>

            <button
              onClick={initAgent}
              disabled={isInitializing}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white font-bold py-3 px-4 rounded-lg transition flex items-center justify-center gap-2"
            >
              {isInitializing ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Initializing... (Downloads ~1-2GB)
                </>
              ) : (
                "Start Engine"
              )}
            </button>

            {isInitializing && (
              <div className="mt-4 p-3 bg-gray-900 rounded border border-gray-700 text-xs font-mono text-green-400 h-32 overflow-y-auto">
                {thoughts.map((t, i) => <div key={i}>{t}</div>)}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white flex flex-col">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 p-4 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-2">
          <Database className="w-6 h-6 text-blue-400" />
          <h1 className="font-bold text-lg">Local SQL Agent</h1>
        </div>
        <div className="flex items-center gap-4 text-sm text-gray-400">
          <span className={cn("flex items-center gap-1.5", status !== 'idle' ? "text-yellow-400" : "text-green-400")}>
            <span className="w-2 h-2 rounded-full bg-current animate-pulse" />
            <span data-testid="status-indicator">{status === 'idle' ? 'Ready' : status}</span>
          </span>
          <Settings className="w-5 h-5 cursor-pointer hover:text-white" />
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Chat Area */}
        <div className="flex-1 flex flex-col relative">
          <div className="flex-1 overflow-y-auto p-4 space-y-6">
            {messages.map((m, i) => (
              <div key={i} className={cn("flex gap-4 max-w-3xl mx-auto", m.role === 'user' ? "flex-row-reverse" : "")} data-testid={`message-${m.role}`}>
                <div className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
                  m.role === 'user' ? "bg-blue-600" : "bg-emerald-600"
                )}>
                  {m.role === 'user' ? "U" : "AI"}
                </div>
                <div className={cn(
                  "rounded-2xl p-4 max-w-[80%]",
                  m.role === 'user' ? "bg-blue-600 text-white rounded-tr-none" : "bg-gray-800 border border-gray-700 text-gray-100 rounded-tl-none"
                )} data-testid={`message-content-${m.role}`}>
                  <p className="whitespace-pre-wrap">{m.content}</p>

                  {m.sql && (
                    <div className="mt-4 bg-gray-950 rounded p-3 text-xs font-mono border border-gray-700 overflow-x-auto">
                      <div className="text-gray-500 mb-1">Generated SQL:</div>
                      <code className="text-emerald-400">{m.sql}</code>
                    </div>
                  )}

                  {m.data && m.data.length > 0 && (
                    <div className="mt-4 overflow-x-auto">
                      <table className="min-w-full text-xs text-left text-gray-400">
                        <thead className="bg-gray-900 uppercase font-medium">
                          <tr>
                            {Object.keys(m.data[0]).map((k) => (
                              <th key={k} className="px-3 py-2 border-b border-gray-700">{k}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {m.data.slice(0, 5).map((row: any, idx: number) => (
                            <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/50">
                              {Object.values(row).map((v: any, vIdx) => (
                                <td key={vIdx} className="px-3 py-2">{String(v)}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {m.data.length > 5 && <div className="text-center text-xs text-gray-500 mt-2">Showing 5 of {m.data.length} rows</div>}
                    </div>
                  )}

                  {m.role === 'assistant' && i === messages.length - 1 && (
                    <div className="mt-4 flex items-center gap-2 border-t border-gray-700/50 pt-3">
                      <span className="text-xs text-gray-500">Was this helpful?</span>
                      <button
                        onClick={() => handleFeedback(1)}
                        className="p-1 hover:text-green-400 transition"
                        title="Yes, it was helpful"
                      >
                        <ThumbsUp className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleFeedback(-1)}
                        className="p-1 hover:text-red-400 transition"
                        title="No, it wasn't helpful"
                      >
                        <ThumbsDown className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Status / Thoughts indicator during processing */}
            {status !== 'idle' && (
              <div className="max-w-3xl mx-auto w-full">
                <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700/50 animate-in fade-in slide-in-from-bottom-2">
                  <div className="flex items-center gap-2 text-sm text-blue-400 font-medium mb-2" data-testid="thinking-status">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {status.charAt(0).toUpperCase() + status.slice(1)}...
                  </div>
                  <div className="text-xs font-mono text-gray-400 space-y-1 max-h-32 overflow-y-auto">
                    {thoughts.slice(-5).map((t, i) => ( // Show last 5 thoughts
                      <div key={i} className="border-l-2 border-gray-700 pl-2">{t}</div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input Area */}
          <div className="p-4 bg-gray-800 border-t border-gray-700">
            <form onSubmit={handleSubmit} className="max-w-3xl mx-auto relative">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about fantasy stats (e.g., 'Who had the most rushing yards in 2021?')"
                disabled={status !== 'idle'}
                className="w-full bg-gray-900 border border-gray-600 rounded-xl py-4 pl-4 pr-12 text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none disabled:opacity-50"
                data-testid="chat-input"
              />
              <button
                type="submit"
                disabled={!input.trim() || status !== 'idle'}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-blue-600 rounded-lg text-white hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 transition"
              >
                <Send className="w-5 h-5" />
              </button>
            </form>
          </div>
        </div>
      </div>
    </div >
  );
}

export default App;
