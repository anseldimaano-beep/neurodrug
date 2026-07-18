import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/components/query-provider";
import AuthGuard from "@/components/auth-guard";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "NeuroDrug AI — Rare Cancer Drug Repurposing",
  description: "Heterogeneous Graph Neural Network platform for rare cancer drug repurposing using multi-omics knowledge graphs.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <QueryProvider>
          <AuthGuard>{children}</AuthGuard>
        </QueryProvider>
      </body>
    </html>
  );
}
