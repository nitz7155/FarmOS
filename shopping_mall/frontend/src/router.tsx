import { createBrowserRouter } from 'react-router-dom';
import App from './App';
import HomePage from '@/pages/HomePage';
import ProductListPage from '@/pages/ProductListPage';
import ProductDetailPage from '@/pages/ProductDetailPage';
import SearchPage from '@/pages/SearchPage';
import CartPage from '@/pages/CartPage';
import OrderPage from '@/pages/OrderPage';
import OrderCompletePage from '@/pages/OrderCompletePage';
import MyPage from '@/pages/MyPage';
import MyOrdersPage from '@/pages/MyOrdersPage';
import WishlistPage from '@/pages/WishlistPage';
import StorePage from '@/pages/StorePage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'products', element: <ProductListPage /> },
      { path: 'products/:id', element: <ProductDetailPage /> },
      { path: 'search', element: <SearchPage /> },
      { path: 'cart', element: <CartPage /> },
      { path: 'order', element: <OrderPage /> },
      { path: 'order/complete', element: <OrderCompletePage /> },
      { path: 'mypage', element: <MyPage /> },
      { path: 'mypage/orders', element: <MyOrdersPage /> },
      { path: 'mypage/wishlist', element: <WishlistPage /> },
      { path: 'store/:id', element: <StorePage /> },
    ],
  },
]);
