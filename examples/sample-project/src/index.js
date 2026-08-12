import express from 'express';
import { OrderService } from './services/order.js';

const app = express();
export function createApp() { return app; }
app.listen(3000);
