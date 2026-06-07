import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "SViam Voice Interviewer",
  description: "Live AI voice interview — pick a language and strictness, and talk.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
