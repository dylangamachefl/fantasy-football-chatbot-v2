import React from 'react';
import { Send, Trophy } from 'lucide-react';
import { ChatMessage } from './ChatMessage';
import type { Message } from '../types';

interface ChatAreaProps {
  messages: Message[];
  status: string;
  input: string;
  setInput: (val: string) => void;
  handleSubmit: (e: React.FormEvent) => void;
  handleFeedback: (val: number) => void;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
}

export function ChatArea({ messages, status, input, setInput, handleSubmit, handleFeedback, messagesEndRef }: ChatAreaProps) {

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as any);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 relative bg-[linear-gradient(to_bottom,rgba(10,14,26,0.8),rgba(10,14,26,1)),url('https://www.transparenttextures.com/patterns/carbon-fibre.png')]">
      <div className="flex-1 min-h-0 overflow-y-auto p-6 space-y-8 scrollbar-styled">
        <div className="max-w-4xl mx-auto space-y-8 pb-12">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full py-20 text-center opacity-50">
              <Trophy className="w-16 h-16 text-yellow-600 mb-6" />
              <h2 className="text-2xl font-black italic uppercase tracking-tighter">Sports Desk is Open</h2>
              <p className="max-w-xs text-sm text-gray-400 mt-2 font-medium">Ask about stats, match history, or league lore.</p>
            </div>
          )}

          {messages.map((m, i) => (
            <ChatMessage
              key={i}
              message={m}
              isLast={i === messages.length - 1}
              onFeedback={handleFeedback}
            />
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className="p-6 bg-gray-900/50 backdrop-blur-xl border-t border-gray-800 relative z-10">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto relative group">
          <div className="absolute -inset-1 bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl blur opacity-20 group-focus-within:opacity-40 transition duration-500" />
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Submit query to Sports Desk logic room..."
            disabled={status !== 'idle'}
            rows={1}
            className="relative w-full bg-gray-950 border border-gray-800 rounded-2xl py-5 pl-6 pr-16 text-white text-lg placeholder-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none disabled:opacity-50 transition-all font-medium italic tracking-tight resize-none overflow-hidden"
            data-testid="chat-input"
            style={{ minHeight: '68px' }}
          />
          <button
            type="submit"
            disabled={!input.trim() || status !== 'idle'}
            className="absolute right-3 top-1/2 -translate-y-1/2 p-3 bg-blue-600 rounded-xl text-white hover:bg-blue-500 disabled:bg-gray-800 disabled:text-gray-600 transition-all shadow-lg active:scale-95 z-20"
          >
            <Send className="w-6 h-6" />
          </button>
        </form>
      </div>
    </div>
  );
}
