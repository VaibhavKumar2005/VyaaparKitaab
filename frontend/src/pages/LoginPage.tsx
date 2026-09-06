import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    try {
      await login(email, password);
      navigate('/app/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in');
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-md items-center px-4">
      <form onSubmit={onSubmit} className="w-full rounded-[2rem] border border-white/10 bg-slate-950/75 p-8 shadow-glow backdrop-blur-xl">
        <h1 className="font-[Space_Grotesk] text-3xl font-bold text-white">Welcome back</h1>
        <p className="mt-2 text-sm text-slate-400">Sign in to manage your store notebook.</p>
        <label className="mt-6 block text-sm text-slate-300">
          Email
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none focus:border-sky-400" />
        </label>
        <label className="mt-4 block text-sm text-slate-300">
          Password
          <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none focus:border-sky-400" />
        </label>
        {error ? <p className="mt-4 text-sm text-red-300">{error}</p> : null}
        <button className="mt-6 w-full rounded-2xl bg-sky-400 px-4 py-3 font-semibold text-slate-950">Sign in</button>
        <p className="mt-4 text-sm text-slate-400">
          Need an account? <Link to="/register" className="text-sky-300">Register</Link>
        </p>
      </form>
    </div>
  );
}