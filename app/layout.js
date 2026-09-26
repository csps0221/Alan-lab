export const metadata = {
  title: "我的科學實驗室",
  description: "Next.js App",
};

export default function RootLayout({ children }) {
  return (
    <html lang="zh-TW">
      <body style={{ margin: 0 }}>{children}</body>
    </html>
  );
}
