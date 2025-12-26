import { Button } from '@/components/ui/button';
import { PlaceHolderImages } from '@/lib/placeholder-images';
import Image from 'next/image';
import Link from 'next/link';
import { TrendingUp } from 'lucide-react';

export default function LandingPage() {
  const heroImage = PlaceHolderImages.find((img) => img.id === 'hero');

  return (
    <div className="flex flex-col min-h-screen">
      <header className="px-4 lg:px-6 h-14 flex items-center bg-background/80 backdrop-blur-sm fixed top-0 left-0 right-0 z-50">
        <Link href="#" className="flex items-center justify-center" prefetch={false}>
          <TrendingUp className="h-6 w-6 text-primary" />
          <span className="sr-only">StockerPro</span>
        </Link>
        <nav className="ml-auto flex gap-4 sm:gap-6">
          <Button asChild variant="ghost">
            <Link href="/login" prefetch={false}>
              Login
            </Link>
          </Button>
          <Button asChild>
            <Link href="/signup" prefetch={false}>
              Get Started
            </Link>
          </Button>
        </nav>
      </header>
      <main className="flex-1">
        <section className="relative w-full pt-12 md:pt-24 lg:pt-32">
          {heroImage && (
            <Image
              src={heroImage.imageUrl}
              alt={heroImage.description}
              fill
              className="object-cover -z-10 brightness-50"
              priority
              data-ai-hint={heroImage.imageHint}
            />
          )}
          <div className="container px-4 md:px-6 text-center text-primary-foreground">
            <div className="flex flex-col items-center space-y-4">
              <div className="space-y-2">
                <h1 className="text-3xl font-bold tracking-tighter sm:text-5xl xl:text-6xl/none">
                  Your Personal Stock Watchlist Companion
                </h1>
                <p className="max-w-[600px] mx-auto text-primary-foreground/80 md:text-xl">
                  Track your favorite stocks, set price targets, and get instant alerts. StockerPro is the ultimate tool
                  for smart investing.
                </p>
              </div>
              <div className="space-x-4">
                <Button asChild size="lg">
                  <Link href="/signup" prefetch={false}>
                    Sign Up Now
                  </Link>
                </Button>
              </div>
            </div>
          </div>
        </section>

        <section className="w-full py-12 md:py-24 lg:py-32 bg-background">
          <div className="container px-4 md:px-6">
            <div className="grid gap-6 items-center">
              <div className="flex flex-col justify-center space-y-4 text-center">
                <div className="space-y-2">
                  <h2 className="text-3xl font-bold tracking-tighter sm:text-5xl">
                    Powerful Features for Every Investor
                  </h2>
                  <p className="max-w-[900px] text-muted-foreground md:text-xl/relaxed lg:text-base/relaxed xl:text-xl/relaxed mx-auto">
                    From real-time price syncing to instant buy/sell alerts, we've got you covered.
                  </p>
                </div>
              </div>
              <div className="mx-auto grid items-start gap-8 sm:max-w-4xl sm:grid-cols-2 md:gap-12 lg:max-w-5xl lg:grid-cols-3">
                <div className="grid gap-1 text-center">
                  <h3 className="text-lg font-bold">Stock Watchlist</h3>
                  <p className="text-sm text-muted-foreground">
                    Create and manage your personal watchlist. Add stocks, specify target prices, and track your
                    portfolio with ease.
                  </p>
                </div>
                <div className="grid gap-1 text-center">
                  <h3 className="text-lg font-bold">Real-time Price Sync</h3>
                  <p className="text-sm text-muted-foreground">
                    Our app automatically syncs with market data to provide you with up-to-the-minute stock prices.
                  </p>
                </div>
                <div className="grid gap-1 text-center">
                  <h3 className="text-lg font-bold">Buy/Sell Alerts</h3>
                  <p className="text-sm text-muted-foreground">
                    Get instant notifications when your stocks hit their target buy or sell prices. Never miss an
                    opportunity.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
      <footer className="flex flex-col gap-2 sm:flex-row py-6 w-full shrink-0 items-center px-4 md:px-6 border-t">
        <p className="text-xs text-muted-foreground">&copy; 2024 StockerPro. All rights reserved.</p>
      </footer>
    </div>
  );
}
