import { createOrder } from './services/order.js';
export function start() {
  return createOrder({ amount: 100 });
}
