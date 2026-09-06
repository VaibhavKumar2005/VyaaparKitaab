import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: '', password: '', full_name: '', phone: '' });
  const [error, setError] = useState('');

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    try {
      await register(form);
      navigate('/app/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to register');
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-md items-center px-4">
      <form onSubmit={onSubmit} className="w-full rounded-[2rem] border border-white/10 bg-slate-950/75 p-8 shadow-glow backdrop-blur-xl">
        <h1 className="font-[Space_Grotesk] text-3xl font-bold text-white">Create account</h1>
        <p className="mt-2 text-sm text-slate-400">Set up your VyaparKitaab workspace.</p>
        {(['email', 'password', 'full_name', 'phone'] as const).map((field) => (
          <label key={field} className="mt-4 block text-sm text-slate-300">
            {field.replace('_', ' ')}
            <input
              value={form[field]}
              onChange={(e) => setForm((current) => ({ ...current, [field]: e.target.value }))}
              type={field === 'password' ? 'password' : field === 'email' ? 'email' : 'text'}
              className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none focus:border-violet-400"
            />
          </label>
        ))}
        {error ? <p className="mt-4 text-sm text-red-300">{error}</p> : null}
        <button className="mt-6 w-full rounded-2xl bg-violet-400 px-4 py-3 font-semibold text-slate-950">Register</button>
        <p className="mt-4 text-sm text-slate-400">
          Already have an account? <Link to="/login" className="text-sky-300">Login</Link>
        </p>
      </form>
    </div>
  );
}