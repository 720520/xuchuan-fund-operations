import type { Metadata } from 'next';
import { headers } from 'next/headers';
import './globals.css';
import './workspace.css';

export async function generateMetadata(): Promise<Metadata> {
  const host = (await headers()).get('host') || 'localhost:3000';
  // Use the request host, never forwarded host headers. Accept only local or Sites-owned origins.
  const trusted =
    /^(localhost|127\.0\.0\.1)(:\d+)?$/.test(host) ||
    /^[a-z0-9.-]+\.(chatgpt-team\.site|chatgpt\.site|chatgpt\.com)$/.test(host);
  const origin = trusted
    ? `${host.startsWith('localhost') || host.startsWith('127.') ? 'http' : 'https'}://${host}`
    : 'http://localhost:3000';
  const title = '序川 · 基金运营工作台 | 设计预览';
  const description = '基金运营工作台第一阶段高保真原型，全部为虚构演示数据。';
  return {
    title,
    description,
    metadataBase: new URL(origin),
    icons: { icon: '/favicon.svg' },
    openGraph: {
      title,
      description,
      images: [
        { url: new URL('/og.png', origin).href, alt: '序川 · 基金运营工作台' },
      ],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [new URL('/og.png', origin).href],
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
