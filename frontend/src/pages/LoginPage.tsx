import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuth } from '../contexts/AuthContext';
import { loginSchema, LoginValues } from '../schemas/auth';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const { register, handleSubmit, setError, formState: { errors, isSubmitting } } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = async (values: LoginValues) => {
    try {
      await login(values.email, values.password);
      navigate('/app/dashboard');
    } catch (err) {
      setError('root', { message: err instanceof Error ? err.message : 'Unable to sign in' });
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-md items-center px-4">
      <form onSubmit={handleSubmit(onSubmit)} className="w-full rounded-[2rem] border border-white/10 bg-slate-950/75 p-8 shadow-glow backdrop-blur-xl">
        <h1 className="font-[Space_Grotesk] text-3xl font-bold text-white">Welcome back</h1>
        <p className="mt-2 text-sm text-slate-400">Sign in to manage your store notebook.</p>
        <label className="mt-6 block text-sm text-slate-300">
          Email
          <input {...register('email')} id="email" type="email" className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none focus:border-sky-400" />
          {errors.email ? <span className="mt-1 block text-xs text-red-300">{errors.email.message}</span> : null}
        </label>
        <label className="mt-4 block text-sm text-slate-300">
          Password
          <input {...register('password')} id="password" type="password" className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none focus:border-sky-400" />
          {errors.password ? <span className="mt-1 block text-xs text-red-300">{errors.password.message}</span> : null}
        </label>
        {errors.root ? <p role="alert" className="mt-4 text-sm text-red-300">{errors.root.message}</p> : null}
        <button disabled={isSubmitting} className="mt-6 w-full rounded-2xl bg-sky-400 px-4 py-3 font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-60">
          {isSubmitting ? 'Signing in...' : 'Sign in'}
        </button>
        <p className="mt-4 text-sm text-slate-400">
          Need an account? <Link to="/register" className="text-sky-300">Register</Link>
        </p>
      </form>
    </div>
  );
}