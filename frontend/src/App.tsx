import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import { ThemeProvider } from "./components/Theme";

export default function App() {
    return <ThemeProvider>
        <div className="w-screen h-screen flex flex-col dark:bg-zinc-900">
            <Header />
            <div className="flex-1 flex flex-row">
                <Sidebar />
                <div className="flex-1 rounded-tl-4xl dark:bg-black/30"></div>
            </div>
        </div>
    </ThemeProvider>;
}