import { useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Nav from "./components/Nav";
import LoginModal from "./components/LoginModal";
import Landing from "./pages/Landing";
import Launch from "./pages/Launch";
import Verify from "./pages/Verify";
import Cashback from "./pages/Cashback";
import Profile from "./pages/Profile";

export default function App() {
  const [loginOpen, setLoginOpen] = useState(false);

  return (
    <BrowserRouter>
      <div className="scanlines min-h-full flex flex-col">
        <Nav onLogin={() => setLoginOpen(true)} />
        <main className="flex-1">
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/launch" element={<Launch />} />
            <Route path="/verify" element={<Verify />} />
            <Route path="/cashback" element={<Cashback />} />
            <Route path="/profile" element={<Profile />} />
          </Routes>
        </main>
        <LoginModal open={loginOpen} onClose={() => setLoginOpen(false)} />
      </div>
    </BrowserRouter>
  );
}
