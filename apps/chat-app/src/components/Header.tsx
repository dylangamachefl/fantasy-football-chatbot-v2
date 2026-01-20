import { Radio, Settings, Menu, Download, ChevronDown } from 'lucide-react';
import { cn } from '../lib/utils';
import Logger from '../lib/logger';
import { useState } from 'react';

interface HeaderProps {
  status: string;
  managerIdentity: string | null;
  onSwitchIdentity: () => void;
  onToggleSidePanel: () => void;
}

export function Header({ status, managerIdentity, onSwitchIdentity, onToggleSidePanel }: HeaderProps) {
  const [showExportMenu, setShowExportMenu] = useState(false);
  const stats = Logger.getStats();

  const handleExport = (type: 'failures' | 'successes' | 'all' | 'raw') => {
    if (type === 'failures') {
      Logger.exportFailuresForTeacher();
    } else if (type === 'successes') {
      Logger.exportSuccessesAsGolden();
    } else if (type === 'all') {
      Logger.exportAllWithFeedback();
    } else if (type === 'raw') {
      Logger.exportLogs();
    }
    setShowExportMenu(false);
  };

  return (
    <header className="bg-gray-900/80 backdrop-blur-md border-b border-gray-800 p-4 flex items-center justify-between shadow-2xl relative z-20">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidePanel}
          className="p-2 -ml-2 xl:hidden text-gray-400 hover:text-white transition-colors"
          aria-label="Toggle Side Panel"
        >
          <Menu className="w-6 h-6" />
        </button>
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

          {/* Export Menu */}
          <div className="relative">
            <button
              onClick={() => setShowExportMenu(!showExportMenu)}
              className="p-2 hover:bg-gray-800 rounded-lg transition-colors group flex items-center gap-1"
              title="Export Logs"
            >
              <Download className="w-5 h-5" />
              <ChevronDown className="w-3 h-3" />
            </button>

            {showExportMenu && (
              <div className="absolute right-0 mt-2 w-72 bg-gray-900 border border-gray-800 rounded-lg shadow-xl overflow-hidden z-50">
                <div className="p-3 border-b border-gray-800 bg-gray-950">
                  <div className="text-xs font-bold text-gray-400 uppercase tracking-wider">Export Logs</div>
                  <div className="text-[10px] text-gray-600 mt-1">
                    {stats.totalQueries} queries · {stats.totalFailures} failures · {stats.totalFeedback - stats.totalFailures} successes
                  </div>
                </div>
                <div className="p-2">
                  <button
                    onClick={() => handleExport('failures')}
                    disabled={stats.totalFailures === 0}
                    className="w-full text-left px-3 py-2 rounded hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <div className="font-semibold text-sm text-red-400">Export Failures for Teacher</div>
                    <div className="text-xs text-gray-500 mt-0.5">Downvoted queries ({stats.totalFailures})</div>
                  </button>
                  <button
                    onClick={() => handleExport('successes')}
                    disabled={stats.totalFeedback - stats.totalFailures === 0}
                    className="w-full text-left px-3 py-2 rounded hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <div className="font-semibold text-sm text-green-400">Export Successes as Golden</div>
                    <div className="text-xs text-gray-500 mt-0.5">Upvoted queries ({stats.totalFeedback - stats.totalFailures})</div>
                  </button>
                  <button
                    onClick={() => handleExport('all')}
                    disabled={stats.totalFeedback === 0}
                    className="w-full text-left px-3 py-2 rounded hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <div className="font-semibold text-sm text-blue-400">Export All with Feedback</div>
                    <div className="text-xs text-gray-500 mt-0.5">Complete data ({stats.totalFeedback} total)</div>
                  </button>
                  <button
                    onClick={() => handleExport('raw')}
                    className="w-full text-left px-3 py-2 rounded hover:bg-gray-800 transition-colors"
                  >
                    <div className="font-semibold text-sm text-gray-300">Export Raw Debug Logs</div>
                    <div className="text-xs text-gray-500 mt-0.5">Full localStorage log dump</div>
                  </button>
                </div>
              </div>
            )}
          </div>

          <button
            onClick={onSwitchIdentity}
            className="p-2 hover:bg-gray-800 rounded-lg transition-colors group"
            title="Identity Settings"
          >
            <Settings className="w-5 h-5 group-hover:rotate-90 transition-transform duration-500" />
          </button>
        </div>
      </div>
    </header>
  );
}
