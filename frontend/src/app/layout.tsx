import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'  // This is crucial - it imports Tailwind and shadcn styles

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
    title: 'Learning Agent',
    description: 'Personalized learning recommendations',
}

export default function RootLayout({
    children,
}: {
    children: React.ReactNode
}) {
    return (
        <html lang="en">
            <body className={`${inter.className} min-h-screen bg-gray-50 antialiased`}>
                {children}
            </body>
        </html>
    )
}
