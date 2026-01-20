import React, { useState, useEffect, useRef } from 'react';
import { Agent } from './lib/agent';
import { Brain, Loader2 } from 'lucide-react';
import { IdentityCheck } from './components/IdentityCheck';
import { Header } from './components/Header';
import { SidePanel } from './components/SidePanel';
import { Ticker } from './components/Ticker';
import { ChatArea } from './components/ChatArea';
import type { Message } from './types';

const MODELS = {
  primary: "Qwen2.5-1.5B-Instruct-q4f16_1-MLC",
};

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [agent, setAgent] = useState<Agent | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const [thoughts, setThoughts] = useState<string[]>([]);
  const [isInitializing, setIsInitializing] = useState(false);
  const [managerIdentity, setManagerIdentity] = useState<string | null>(() => localStorage.getItem('ff_manager_identity'));
  const [isSidePanelOpen, setIsSidePanelOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const initAgent = async () => {
    setIsInitializing(true);
    const newAgent = new Agent((state) => {
      setStatus(state.status);
      setThoughts([...state.thoughts]); // Copy to trigger re-render
    });

    try {
      await newAgent.init(MODELS.primary);
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
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !agent || status !== 'idle') return;

    const userMsg: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setThoughts([]); // Clear previous thoughts
    if (window.innerWidth < 1280) setIsSidePanelOpen(false); // Close side panel on mobile after submit

    try {
      // Filter history for context (last 10 messages)
      const history = messages.slice(-10).map(m => ({
        role: m.role,
        content: m.content
      }));

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
    return <IdentityCheck onSelect={selectManager} />;
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
            <button
              onClick={initAgent}
              disabled={isInitializing}
              className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-800 text-white font-black py-4 px-4 rounded-xl transition flex items-center justify-center gap-3 uppercase tracking-tighter cursor-pointer"
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
    <div className="h-screen bg-gray-950 text-white flex flex-col font-sans selection:bg-blue-500/30">
      <Header
        status={status}
        managerIdentity={managerIdentity}
        onSwitchIdentity={handleSwitchManager}
        onToggleSidePanel={() => setIsSidePanelOpen(!isSidePanelOpen)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex relative overflow-hidden">
        <SidePanel thoughts={thoughts} isOpen={isSidePanelOpen} />

        <div className="flex-1 flex flex-col min-w-0 relative">
          <ChatArea
            messages={messages}
            status={status}
            input={input}
            setInput={setInput}
            handleSubmit={handleSubmit}
            handleFeedback={handleFeedback}
            messagesEndRef={messagesEndRef}
          />
          <Ticker status={status} managerIdentity={managerIdentity} />
        </div>
      </div>
    </div>
  );
}

export default App;
