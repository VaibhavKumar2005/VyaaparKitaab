import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuth } from '../contexts/AuthContext';
import { registerSchema, RegisterValues } from '../schemas/auth';

const inputClass =
  'mt-1.5 w-full rounded-md border border-rule bg-canvas-raised px-3.5 py-2.5 text-sm outline-none focus:border-navy';

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const {
    register: field,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({
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
    <div className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-4 py-10">
      <Link to="/" className="font-display text-2xl font-bold text-navy">
        VyaparKitaab
      </Link>
      <h1 className="mt-6 font-display text-3xl font-bold">Create account</h1>
      <p className="mt-1 text-sm text-ink-soft">Start your shop's books.</p>

      <form onSubmit={handleSubmit(onSubmit)} className="mt-8 space-y-4" noValidate>
        <div>
          <label htmlFor="full_name" className="text-sm font-medium">Full name</label>
          <input {...field('full_name')} id="full_name" autoComplete="name" className={inputClass} />
          {errors.full_name ? <p className="mt-1 text-xs text-due">{errors.full_name.message}</p> : null}
        </div>
        <div>
          <label htmlFor="email" className="text-sm font-medium">Email</label>
          <input {...field('email')} id="email" type="email" autoComplete="email" className={inputClass} />
          {errors.email ? <p className="mt-1 text-xs text-due">{errors.email.message}</p> : null}
        </div>
        <div>
          <label htmlFor="phone" className="text-sm font-medium">
            Mobile number <span className="font-normal text-ink-faint">(optional)</span>
          </label>
          <input {...field('phone')} id="phone" type="tel" autoComplete="tel" className={inputClass} />
        </div>
        <div>
          <label htmlFor="password" className="text-sm font-medium">Password</label>
          <input {...field('password')} id="password" type="password" autoComplete="new-password" className={inputClass} />
          {errors.password ? <p className="mt-1 text-xs text-due">{errors.password.message}</p> : null}
        </div>
        {errors.root ? (
          <p role="alert" className="rounded-md bg-due-tint p-3 text-sm text-due">{errors.root.message}</p>
        ) : null}
        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-md bg-navy px-4 py-2.5 font-semibold text-white hover:bg-navy-dark disabled:opacity-60"
        >
          {isSubmitting ? 'Creating account…' : 'Create account'}
        </button>
      </form>

      <p className="mt-6 text-sm text-ink-soft">
        Already registered? <Link to="/login" className="font-semibold text-navy hover:underline">Sign in</Link>
      </p>
    </div>
  );
}