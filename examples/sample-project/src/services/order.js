import { PaymentService } from './payment.js';

export class OrderService {
  constructor() { this.payment = new PaymentService(); }
  async createOrder(input) { return this.payment.charge(input); }
  async cancelOrder(id) { return id; }
}
