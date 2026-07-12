export type UserRole = 'admin' | 'developer' | 'user' | 'guest';

export interface User {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  last_login?: string | null;
  profile_picture?: string | null;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export interface ConversationHistory {
  id: number;
  user_id: number;
  session_id: string;
  prompt: string;
  response: string;
  created_at: string;
}

export interface UserSetting {
  id: number;
  user_id: number;
  key: string;
  value: string;
  created_at: string;
  updated_at: string;
}

export interface ActivityLog {
  id: number;
  user_id?: number | null;
  action: string;
  details?: string | null;
  ip_address?: string | null;
  created_at: string;
}
