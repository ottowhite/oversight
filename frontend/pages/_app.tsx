import type { AppProps } from 'next/app';
import '../styles/globals.css';

export default function MyApp({ Component, pageProps }: AppProps) {
  return (
    <div data-theme="chatgpt" className="min-h-screen bg-base-100 text-base-content">
      <Component {...pageProps} />
    </div>
  );
}
