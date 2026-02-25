import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    try {
      const url = isRegister ? '/api/auth/register' : '/api/auth/login';
      const body = isRegister
        ? JSON.stringify({ email, name, password })
        : new URLSearchParams({ username: email, password });
      const headers: Record<string, string> = isRegister
        ? { 'Content-Type': 'application/json' }
        : { 'Content-Type': 'application/x-www-form-urlencoded' };

      const res = await fetch(url, { method: 'POST', headers, body });
      if (!res.ok) throw new Error((await res.json()).detail || 'Auth failed');
      const data = await res.json();
      localStorage.setItem('token', data.access_token);
      navigate('/chat');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full bg-white rounded-lg shadow p-8">
        <h1 className="text-2xl font-bold text-center mb-6">Sense</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          {isRegister && (
            <input
              type="text"
              placeholder="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 border rounded"
              required
            />
          )}
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-3 py-2 border rounded"
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 border rounded"
            required
          />
          {error && <p className="text-red-600 text-sm">{error}</p>}
          <button
            type="submit"
            className="w-full bg-gray-900 text-white py-2 rounded hover:bg-gray-800"
          >
            {isRegister ? 'Register' : 'Login'}
          </button>
        </form>
        <button
          onClick={() => setIsRegister(!isRegister)}
          className="mt-4 text-sm text-gray-500 hover:text-gray-700 w-full text-center"
        >
          {isRegister ? 'Already have an account? Login' : "Don't have an account? Register"}
        </button>
      </div>
    </div>
  );
}
