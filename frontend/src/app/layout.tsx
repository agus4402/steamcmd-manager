import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SteamCMD Server Manager",
  description: "Self-hosted panel to manage SteamCMD game servers",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
