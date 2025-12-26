import { Watchlist } from "@/components/dashboard/watchlist";
import { initialStocks } from "@/lib/data";

export default function DashboardPage() {
  // In a real app, you would fetch user-specific watchlist data here.
  const stocks = initialStocks;

  return (
    <>
      <div className="flex items-center">
        <h1 className="text-lg font-semibold md:text-2xl">My Watchlist</h1>
      </div>
      <div
        className="flex flex-1 items-start justify-center rounded-lg border border-dashed shadow-sm"
        x-chunk="dashboard-02-chunk-1"
      >
        <Watchlist initialStocks={stocks} />
      </div>
    </>
  )
}
