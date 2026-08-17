import { charge } from './payment.js';
export async function createOrder(input) {
  const paid = await charge(input.amount);
  return { paid };
}
