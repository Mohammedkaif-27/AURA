import React, { useState, useEffect } from 'react';
import ChatWindow from './components/ChatWindow';
import Auth from './components/Auth';
import { supabase } from './lib/supabase';
import { Toaster } from 'sonner';

export default function App() {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setLoading(false);
    });

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
