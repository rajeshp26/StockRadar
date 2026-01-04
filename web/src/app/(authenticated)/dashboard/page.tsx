import { Watchlist } from "@/components/dashboard/watchlist";

export default function DashboardPage() {
  return (
    <div
      className="flex flex-1 items-start justify-center rounded-lg"
      x-chunk="dashboard-02-chunk-1"
    >
      <Watchlist />
    </div>
  )
}
