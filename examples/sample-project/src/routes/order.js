import { createOrder } from '../services/order.js';
export function checkout(req) {
  return createOrder(req.body);
}
