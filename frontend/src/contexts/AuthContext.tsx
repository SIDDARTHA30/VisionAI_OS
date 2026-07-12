import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';
import { User, AuthState } from '../types';

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Set default base URL for API requests
axios.defaults.baseURL = 'http://localhost:8000';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<AuthState>({
    user: null,
    token: localStorage.getItem('token'),
    refreshToken: localStorage.getItem('refreshToken'),
    isAuthenticated: false,
    isLoading: true,
  });

  // Sync token to Axios authorizations header
  const updateAxiosHeader = (token: string | null) => {
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
      delete axios.defaults.headers.common['Authorization'];
    }
  };

  useEffect(() => {
    const bootstrapAuth = async () => {
      const storedToken = localStorage.getItem('token');
      if (storedToken) {
        updateAxiosHeader(storedToken);
        try {
          // Fetch current user verification status
          const response = await axios.get<User>('/api/v1/auth/me');
          setState({
            user: response.data,
            token: storedToken,
            refreshToken: localStorage.getItem('refreshToken'),
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error) {
          // If expired or invalid, attempt token refresh
          const storedRefresh = localStorage.getItem('refreshToken');
          if (storedRefresh) {
            try {
              const res = await axios.post('/api/v1/auth/refresh', null, {
                params: { refresh_token_str: storedRefresh },
              });
              const { access_token, refresh_token, name, role } = res.data;
              
              localStorage.setItem('token', access_token);
              localStorage.setItem('refreshToken', refresh_token);
              updateAxiosHeader(access_token);
              
              const userRes = await axios.get<User>('/api/v1/auth/me');
              setState({
                user: userRes.data,
                token: access_token,
                refreshToken: refresh_token,
                isAuthenticated: true,
                isLoading: false,
              });
              return;
            } catch (err) {
              // Refresh failed
              console.error('Refresh token expired or invalid', err);
            }
          }
          // Clear credentials
          logout();
        }
      } else {
        setState((prev) => ({ ...prev, isLoading: false }));
      }
    };

    bootstrapAuth();
  }, []);

  const login = async (email: string, password: string) => {
    setState((prev) => ({ ...prev, isLoading: true }));
    try {
      const params = new URLSearchParams();
      params.append('username', email);
      params.append('password', password);

      const response = await axios.post('/api/v1/auth/login', params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });

      const { access_token, refresh_token } = response.data;
      
      localStorage.setItem('token', access_token);
      localStorage.setItem('refreshToken', refresh_token);
      updateAxiosHeader(access_token);

      const userRes = await axios.get<User>('/api/v1/auth/me');
      setState({
        user: userRes.data,
        token: access_token,
        refreshToken: refresh_token,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (error: any) {
      setState((prev) => ({ ...prev, isLoading: false }));
      throw new Error(error.response?.data?.detail || 'Authentication failed');
    }
  };

  const signup = async (name: string, email: string, password: string) => {
    setState((prev) => ({ ...prev, isLoading: true }));
    const payload = {
      name,
      email,
      password,
      role: "user"
    };

    console.log("Signup Payload:", payload);

    try {
      await axios.post('/api/v1/auth/signup', payload);
      setState((prev) => ({ ...prev, isLoading: false }));
    } catch (error: any) {
      console.log("Signup Error:", error.response?.data);
      console.log("Status:", error.response?.status);

      setState((prev) => ({ ...prev, isLoading: false }));
      throw new Error(error.response?.data?.detail || 'Registration failed');
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('refreshToken');
    updateAxiosHeader(null);
    setState({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
    });
  };

  return (
    <AuthContext.Provider value={{ ...state, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
