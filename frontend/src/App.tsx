import { NavLink, Outlet, Route, Routes } from 'react-router-dom';
import About from './pages/About.tsx';
import Home from './pages/Home.tsx';
import ItemDetail from './pages/ItemDetail.tsx';
import Items from './pages/Items.tsx';
import NotFound from './pages/NotFound.tsx';
import WhatsAppSimulator from './whatsapp/WhatsAppSimulator.tsx';

function Layout() {
  return (
    <>
      <nav className="nav">
        <NavLink to="/" end>
          Home
        </NavLink>
        <NavLink to="/items">Items</NavLink>
        <NavLink to="/about">About</NavLink>
        <NavLink to="/whatsapp">WhatsApp</NavLink>
      </nav>
      <main>
        <Outlet />
      </main>
    </>
  );
}

export default function App() {
  return (
    <Routes>
      {/* Full-screen demo of the WhatsApp adapter, outside the app layout. */}
      <Route path="/whatsapp" element={<WhatsAppSimulator />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/items" element={<Items />} />
        <Route path="/items/:id" element={<ItemDetail />} />
        <Route path="/about" element={<About />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
