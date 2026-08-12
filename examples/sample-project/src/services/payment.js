export class PaymentService {
  async charge(input) { return { ok: true, input }; }
  async refund(id) { return { ok: true, id }; }
}
