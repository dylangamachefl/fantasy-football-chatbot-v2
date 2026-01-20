import { useState } from 'react';
import { User, Mic, Radio, Database, ThumbsUp, ThumbsDown, Copy, Check } from 'lucide-react';
import { cn } from '../lib/utils';
import type { Message } from '../types';

interface ChatMessageProps {
  message: Message;
  isLast: boolean;
  onFeedback: (value: number) => void;
}

export function ChatMessage({ message, isLast, onFeedback }: ChatMessageProps) {
  const [copied, setCopied] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState<'up' | 'down' | null>(null);

  const handleCopySql = () => {
    if (message.sql) {
      navigator.clipboard.writeText(message.sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleFeedbackClick = (value: number) => {
    const feedbackType = value === 1 ? 'up' : 'down';
    setFeedbackGiven(feedbackType);
    onFeedback(value);
  };

  return (
    <div className={cn("flex gap-6 animate-in fade-in slide-in-from-bottom-4 duration-500", message.role === 'user' ? "flex-row-reverse" : "")} data-testid={`message-${message.role}`}>
      <div className={cn(
        "w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 border-2 shadow-xl",
        message.role === 'user' ? "bg-blue-600 border-blue-400 rotate-3" : "bg-gray-900 border-gray-700 -rotate-3"
      )}>
        {message.role === 'user' ? <User className="w-6 h-6" /> : <Mic className="w-6 h-6 text-blue-500" />}
      </div>
      <div className={cn(
        "rounded-3xl p-6 max-w-[95%] xl:max-w-[85%] relative",
        message.role === 'user' ? "bg-blue-600 text-white rounded-tr-none shadow-blue-900/20" : "bg-gray-900/80 backdrop-blur-sm border border-gray-800 text-gray-100 rounded-tl-none shadow-black/40"
      )} data-testid={`message-content-${message.role}`}>
        {/* Breaking News Badge */}
        {message.role === 'assistant' && message.content.length > 200 && (
          <div className="absolute -top-3 left-6 bg-yellow-500 text-black text-[10px] font-black uppercase tracking-tighter px-3 py-1 rounded-full italic shadow-lg flex items-center gap-1">
            <Radio className="w-3 h-3 animate-pulse" /> Breaking News
          </div>
        )}

        <p className="text-lg leading-relaxed font-medium selection:bg-yellow-500 selection:text-black whitespace-pre-wrap">{message.content}</p>

        {message.sql && (
          <div className="mt-6 bg-black/50 rounded-2xl border border-gray-800 font-mono text-sm overflow-hidden">
            <div className="flex items-center justify-between p-3 border-b border-gray-800 bg-gray-900/50">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-emerald-500" />
                <span className="text-gray-500 text-xs font-bold uppercase tracking-widest">Live SQL Query Execution</span>
              </div>
              <button
                onClick={handleCopySql}
                className="text-gray-500 hover:text-white transition-colors"
                title="Copy SQL"
              >
                {copied ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
            <div className="p-4 overflow-x-auto">
              <code className="text-emerald-400">{message.sql}</code>
            </div>
          </div>
        )}

        {message.data && message.data.length > 0 && (
          <div className="mt-6 overflow-hidden rounded-2xl border border-gray-800 shadow-2xl bg-gray-950">
            <div className="bg-gray-950 px-4 py-2 border-b border-gray-800 flex items-center justify-between">
              <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Broadcast Data Result</span>
              <span className="text-[10px] font-bold text-blue-500 underline uppercase tracking-tighter cursor-pointer">Export CSV</span>
            </div>
            <div className="overflow-x-auto max-h-[400px] overflow-y-auto scrollbar-thin scrollbar-thumb-gray-800 scrollbar-track-transparent">
              <table className="min-w-full text-xs text-left border-collapse">
                <thead className="bg-gray-950 uppercase font-black text-gray-400 tracking-tighter sticky top-0 z-10 shadow-sm shadow-gray-900/50">
                  <tr>
                    {Object.keys(message.data[0]).map((k) => (
                      <th key={k} className="px-5 py-3 bg-gray-950 border-b border-gray-800 whitespace-nowrap">{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/50">
                  {message.data.map((row: any, idx: number) => (
                    <tr key={idx} className="hover:bg-blue-600/5 transition-colors">
                      {Object.values(row).map((v: any, vIdx) => (
                        <td key={vIdx} className="px-5 py-3 font-medium text-gray-300 whitespace-nowrap">{String(v)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {message.data.length > 20 && (
              <div className="bg-gray-950/50 p-3 text-center text-[10px] font-bold text-gray-600 border-t border-gray-800 uppercase tracking-widest">
                Showing {message.data.length} Rows
              </div>
            )}
          </div>
        )}

        {message.role === 'assistant' && isLast && (
          <div className="mt-6 flex items-center justify-end gap-4 border-t border-gray-800/50 pt-4">
            <span className="text-[10px] font-black text-gray-600 uppercase tracking-widest">
              {feedbackGiven ? (feedbackGiven === 'up' ? 'Thanks! ✓' : 'Noted ✓') : 'Reception Check?'}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => handleFeedbackClick(1)}
                className={`p-2 rounded-lg transition-all group ${feedbackGiven === 'up'
                    ? 'bg-emerald-500/20 text-emerald-400'
                    : 'hover:bg-emerald-500/10 hover:text-emerald-400'
                  }`}
                disabled={feedbackGiven !== null}
              >
                <ThumbsUp className={`w-5 h-5 transition-transform ${feedbackGiven !== 'up' ? 'group-hover:scale-110' : ''}`} />
              </button>
              <button
                onClick={() => handleFeedbackClick(-1)}
                className={`p-2 rounded-lg transition-all group ${feedbackGiven === 'down'
                    ? 'bg-red-500/20 text-red-400'
                    : 'hover:bg-red-500/10 hover:text-red-400'
                  }`}
                disabled={feedbackGiven !== null}
              >
                <ThumbsDown className={`w-5 h-5 transition-transform ${feedbackGiven !== 'down' ? 'group-hover:scale-110' : ''}`} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
