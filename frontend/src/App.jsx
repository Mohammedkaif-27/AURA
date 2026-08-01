import React, { useState, useEffect } from 'react';
import ChatWindow from './components/ChatWindow';
import Auth from './components/Auth';
import { supabase } from './lib/supabase';
import { Toaster } from 'sonner';

export default function App() {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isServerAwake, setIsServerAwake] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setLoading(false);
    });

    const checkHealth = async () => {
      try {
        const url = import.meta.env.VITE_API_URL || 'http://localhost:8000';
        await fetch(`${url}/health`);
        setIsServerAwake(true);
      } catch (err) {
        setIsServerAwake(true);
      }
    };
    checkHealth();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
    });

    return () => subscription.unsubscribe();
  }, []);

  const handleLogout = async () => {
    await supabase.auth.signOut();
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-bg flex flex-col items-center justify-center">
        <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!isServerAwake) {
    return (
      <div className="min-h-screen bg-bg flex flex-col items-center justify-center p-4">
        <div className="flex flex-col items-center space-y-6 max-w-md text-center p-8 bg-bg-secondary border border-border rounded-3xl shadow-sm">
          <div className="w-16 h-16 bg-accent/10 rounded-2xl flex items-center justify-center shadow-inner">
            <div className="w-8 h-8 border-[3px] border-accent border-t-transparent rounded-full animate-spin" />
          </div>
          <div className="space-y-3">
            <h2 className="text-xl font-bold text-text-primary">Waking up AURA Backend</h2>
            <p className="text-sm text-text-secondary leading-relaxed">
              AURA is hosted on a free tier that spins down after inactivity. 
              Please wait a moment while the server boots up... (This usually takes 30-50 seconds).
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!session) {
    return <Auth onAuthSuccess={setSession} />;
  }

  return (
    <>
      <Toaster position="bottom-right" richColors />
      <ChatWindow session={session} onLogout={handleLogout} />
    </>
  );
}
