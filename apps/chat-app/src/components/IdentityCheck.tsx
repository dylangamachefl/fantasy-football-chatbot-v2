import { VALID_OWNER_NAMES } from '../lib/agent';
import { Trophy, User } from 'lucide-react';

interface IdentityCheckProps {
  onSelect: (name: string) => void;
}

export function IdentityCheck({ onSelect }: IdentityCheckProps) {
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
              onClick={() => onSelect(name)}
              className="bg-gray-900 border border-gray-800 hover:border-blue-500 hover:bg-gray-800 p-6 rounded-xl transition group text-center cursor-pointer"
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
