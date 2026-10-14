import type { Metadata } from "next";
import { Fira_Sans, Fira_Code } from "next/font/google";
import "./globals.css";
import { CredentialsProvider } from "@/components/CredentialsModal";
import AppShell from "@/components/shell/AppShell";
import { Toaster } from "sonner";

const firaSans = Fira_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const firaCode = Fira_Code({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SteamCMD Server Manager",
  description: "Self-hosted control panel to manage SteamCMD game servers",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`dark ${firaSans.variable} ${firaCode.variable}`}>
      <head>
        {/* Blocking on purpose: lib/api.ts reads it when its module loads. */}
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script src="/runtime-config.js" />
      </head>
      <body>
        <CredentialsProvider>
          <AppShell>{children}</AppShell>
        </CredentialsProvider>
        <Toaster theme="dark" position="bottom-right" richColors closeButton />
      </body>
    </html>
  );
}
