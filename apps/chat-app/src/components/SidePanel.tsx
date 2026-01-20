import { useEffect, useRef } from 'react';
import { Mic, Download } from 'lucide-react';
import { cn } from '../lib/utils';
import Logger from '../lib/logger';

interface SidePanelProps {
  thoughts: string[];
  isOpen: boolean;
}

export function SidePanel({ thoughts, isOpen }: SidePanelProps) {
  const thoughtsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    thoughtsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thoughts]);

  const handleDownload = () => {
    Logger.exportCurrentTrace(thoughts);
  };

  const mobileClasses = isOpen ? "translate-x-0 flex" : "-translate-x-full hidden";

  return (
    <aside className={cn(
      // Base layout
      "w-80 border-r border-gray-800 flex-col z-10",
      // Animation
      "transition-transform duration-300 ease-in-out",
      // Mobile positioning and background
      "fixed inset-y-0 left-0 bg-gray-950/95 backdrop-blur-xl",
      // Mobile state
      mobileClasses,
      // Desktop Overrides
      "xl:relative xl:flex xl:translate-x-0 xl:bg-gray-900/30"
    )}>
      <div className="p-4 border-b border-gray-800 bg-gray-900/50 flex items-center justify-between pt-20 xl:pt-4">
        <div className="flex items-center gap-2">
          <Mic className="w-4 h-4 text-blue-500" />
          <span className="font-black italic uppercase tracking-tighter text-sm">Live Logic Feed</span>
        </div>
        <button
          onClick={handleDownload}
          disabled={thoughts.length === 0}
          className="p-1 hover:bg-gray-800 rounded-md transition-colors disabled:opacity-30 disabled:cursor-not-allowed group"
          title="Download Logic Feed"
        >
          <Download className="w-4 h-4 text-gray-500 group-hover:text-blue-400 transition-colors" />
        </button>
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
        <div ref={thoughtsEndRef} />
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
  );
}
