export type Message = {
  role: 'user' | 'assistant' | 'system';
  content: string;
  sql?: string;
  data?: any[];
};

export type AgentState = {
  status: 'idle' | 'initializing' | 'thinking' | 'querying' | 'executing' | 'reflecting' | 'answering' | 'error';
  thoughts: string[];
  error?: string;
  identity?: string;
  managerBio?: string;
};

export type WorkingMemory = {
  Manager: string;
  Season: string;
  Player: string;
  Week: string;
  EntityType: 'Manager' | 'Player' | 'League' | 'None'; // New Field
};
