import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "xC — Strategic Partnerships",
  description: "Create a strategic partnership report with xC.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
