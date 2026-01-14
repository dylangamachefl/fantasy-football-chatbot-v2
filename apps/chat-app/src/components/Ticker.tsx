interface TickerProps {
  status: string;
  managerIdentity: string | null;
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

export function Ticker({ status, managerIdentity }: TickerProps) {
  return (
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
  );
}
