import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuth } from '../contexts/AuthContext';
import { registerSchema, RegisterValues } from '../schemas/auth';

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const { register: registerField, handleSubmit, setError, formState: { errors, isSubmitting } } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: '', password: '', full_name: '', phone: '' },
  });

  const onSubmit = async (values: RegisterValues) => {
    try {
      await register(values);
      navigate('/app/dashboard');
    } catch (err) {
      setError('root', { message: err instanceof Error ? err.message : 'Unable to register' });
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-md items-center px-4">
      <form onSubmit={handleSubmit(onSubmit)} className="w-full rounded-[2rem] border border-white/10 bg-slate-950/75 p-8 shadow-glow backdrop-blur-xl">
        <h1 className="font-[Space_Grotesk] text-3xl font-bold text-white">Create account</h1>
        <p className="mt-2 text-sm text-slate-400">Set up your VyaparKitaab workspace.</p>
        <label className="mt-4 block text-sm text-slate-300">
          Full name
          <input {...registerField('full_name')} className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none focus:border-violet-400" />
          {errors.full_name ? <span className="mt-1 block text-xs text-red-300">{errors.full_name.message}</span> : null}
        </label>
        <label className="mt-4 block text-sm text-slate-300">
          Email
          <input {...registerField('email')} type="email" className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none focus:border-violet-400" />
          {errors.email ? <span className="mt-1 block text-xs text-red-300">{errors.email.message}</span> : null}
        </label>
        <label className="mt-4 block text-sm text-slate-300">
          Password
          <input {...registerField('password')} type="password" className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none focus:border-violet-400" />
          {errors.password ? <span className="mt-1 block text-xs text-red-300">{errors.password.message}</span> : null}
        </label>
        <label className="mt-4 block text-sm text-slate-300">
          Phone <span className="text-slate-500">(optional)</span>
          <input {...registerField('phone')} type="tel" className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none focus:border-violet-400" />
        </label>
        {errors.root ? <p role="alert" className="mt-4 text-sm text-red-300">{errors.root.message}</p> : null}
        <button disabled={isSubmitting} className="mt-6 w-full rounded-2xl bg-violet-400 px-4 py-3 font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-60">
          {isSubmitting ? 'Creating account...' : 'Register'}
        </button>
        <p className="mt-4 text-sm text-slate-400">
          Already have an account? <Link to="/login" className="text-sky-300">Login</Link>
        </p>
      </form>
    </div>
  );
}