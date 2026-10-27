import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { AppGuard } from "@/components/shell/app-guard";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-app text-ink lg:grid lg:grid-cols-[280px_minmax(0,1fr)]">
      <Sidebar />
      <div className="min-w-0">
        <Topbar />
        <main className="mx-auto w-full max-w-[1600px] px-4 py-5 sm:px-6 lg:px-8">
          <AppGuard>{children}</AppGuard>
        </main>
      </div>
    </div>
  );
}
