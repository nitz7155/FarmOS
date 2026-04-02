import { Link } from 'react-router-dom';
import SearchBar from './SearchBar';
import { useCart } from '@/hooks/useCart';

export default function Header() {
  const { data: cart } = useCart();
  const itemCount = cart?.items.length ?? 0;

  return (
    <header className="sticky top-0 z-50 bg-white border-b border-gray-200">
      <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between gap-4">
        <Link to="/" className="text-xl font-bold text-[#03C75A] whitespace-nowrap">
          FarmOS 마켓
        </Link>
        <div className="flex-1 max-w-xl">
          <SearchBar />
        </div>
        <nav className="flex items-center gap-4 text-sm whitespace-nowrap">
          <Link to="/cart" className="relative hover:text-[#03C75A]">
            장바구니
            {itemCount > 0 && (
              <span className="absolute -top-2 -right-3 bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
                {itemCount}
              </span>
            )}
          </Link>
          <Link to="/mypage" className="hover:text-[#03C75A]">마이페이지</Link>
        </nav>
      </div>
    </header>
  );
}
