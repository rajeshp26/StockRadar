import { Button } from '@/components/ui/button';
import { PlaceHolderImages } from '@/lib/placeholder-images';
import Image from 'next/image';
import Link from 'next/link';
import { TrendingUp, Activity, Bell, ShieldCheck } from 'lucide-react';

export default function LandingPage() {
  const heroImage = PlaceHolderImages.find((img) => img.id === 'hero');
  const feature1Image = PlaceHolderImages.find((img) => img.id === 'feature1');
  const feature2Image = PlaceHolderImages.find((img) => img.id === 'feature2');
  const feature3Image = PlaceHolderImages.find((img) => img.id === 'feature3');


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
        <section className="relative w-full pt-24 md:pt-32 lg:pt-40 pb-12 md:pb-24 lg:pb-32">
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
                <h1 className="text-4xl font-bold tracking-tighter sm:text-5xl md:text-6xl lg:text-7xl/none">
                  Your Personal Stock Watchlist Companion
                </h1>
                <p className="max-w-[600px] mx-auto text-primary-foreground/80 md:text-xl">
                  Track your favorite stocks, set price targets, and get instant alerts. StockerPro is the ultimate tool
                  for smart investing.
                </p>
              </div>
              <div className="space-x-4 mt-6">
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
            <div className="flex flex-col items-center justify-center space-y-4 text-center mb-12">
              <div className="space-y-2">
                <h2 className="text-3xl font-bold tracking-tighter sm:text-5xl">
                  Powerful Features for Every Investor
                </h2>
                <p className="max-w-[900px] text-muted-foreground md:text-xl/relaxed lg:text-base/relaxed xl:text-xl/relaxed mx-auto">
                  From real-time price syncing to instant buy/sell alerts, we've got you covered.
                </p>
              </div>
            </div>
            <div className="mx-auto grid max-w-5xl items-center gap-6 py-12 lg:grid-cols-3 lg:gap-12">
              <div className="grid gap-4">
                <div className="flex items-center gap-4">
                  <div className="bg-primary rounded-md p-3 flex items-center justify-center">
                    <Activity className="w-6 h-6 text-primary-foreground" />
                  </div>
                  <h3 className="text-xl font-bold">Stock Watchlist</h3>
                </div>
                <p className="text-muted-foreground">
                  Create and manage your personal watchlist. Add stocks, specify target prices, and track your
                  portfolio with ease.
                </p>
                {feature1Image && (
                  <Image
                    src={feature1Image.imageUrl}
                    alt={feature1Image.description}
                    width={400}
                    height={250}
                    className="rounded-lg object-cover"
                    data-ai-hint={feature1Image.imageHint}
                  />
                )}
              </div>
              <div className="grid gap-4">
                <div className="flex items-center gap-4">
                  <div className="bg-primary rounded-md p-3 flex items-center justify-center">
                    <Bell className="w-6 h-6 text-primary-foreground" />
                  </div>
                  <h3 className="text-xl font-bold">Real-time Alerts</h3>
                </div>
                <p className="text-muted-foreground">
                  Get instant notifications when your stocks hit their target buy or sell prices. Never miss an
                  opportunity.
                </p>
                 {feature2Image && (
                  <Image
                    src={feature2Image.imageUrl}
                    alt={feature2Image.description}
                    width={400}
                    height={250}
                    className="rounded-lg object-cover"
                    data-ai-hint={feature2Image.imageHint}
                  />
                )}
              </div>
              <div className="grid gap-4">
                <div className="flex items-center gap-4">
                  <div className="bg-primary rounded-md p-3 flex items-center justify-center">
                    <ShieldCheck className="w-6 h-6 text-primary-foreground" />
                  </div>
                  <h3 className="text-xl font-bold">Secure & Reliable</h3>
                </div>
                <p className="text-muted-foreground">
                  Your data is safe with us. We use industry-standard security practices to protect your information.
                </p>
                 {feature3Image && (
                  <Image
                    src={feature3Image.imageUrl}
                    alt={feature3Image.description}
                    width={400}
                    height={250}
                    className="rounded-lg object-cover"
                    data-ai-hint={feature3Image.imageHint}
                  />
                )}
              </div>
            </div>
          </div>
        </section>
      </main>
      <footer className="flex flex-col gap-2 sm:flex-row py-6 w-full shrink-0 items-center px-4 md:px-6 border-t">
        <p className="text-xs text-muted-foreground">&copy; 2024 StockerPro. All rights reserved.</p>
        <nav className="sm:ml-auto flex gap-4 sm:gap-6">
          <Link href="#" className="text-xs hover:underline underline-offset-4" prefetch={false}>
            Terms of Service
          </Link>
          <Link href="#" className="text-xs hover:underline underline-offset-4" prefetch={false}>
            Privacy
          </Link>
        </nav>
      </footer>
    </div>
  );
}
