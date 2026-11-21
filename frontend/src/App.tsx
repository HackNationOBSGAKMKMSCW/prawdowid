import { NavLink, Route, Routes } from 'react-router-dom';
import About from './pages/About.tsx';
import Home from './pages/Home.tsx';
import ItemDetail from './pages/ItemDetail.tsx';
import Items from './pages/Items.tsx';
import NotFound from './pages/NotFound.tsx';

export default function App() {
  return (
    <>
      <nav className="nav">
        <NavLink to="/" end>
          Home
        </NavLink>
        <NavLink to="/items">Items</NavLink>
        <NavLink to="/about">About</NavLink>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/items" element={<Items />} />
          <Route path="/items/:id" element={<ItemDetail />} />
          <Route path="/about" element={<About />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </>
  );
}
