//+------------------------------------------------------------------+
//|                                                   TradeAgent.mq5 |
//|                        ZeroMQ Bridge for Python Trading Agent     |
//|                        Uses mql-zmq by Ding Li (dingmaotu)       |
//+------------------------------------------------------------------+
#property copyright "TradeAgent"
#property link      "https://github.com/dingmaotu/mql-zmq"
#property version   "1.00"
#property strict

//--- ZMQ library (mql-zmq by dingmaotu)
#include <Zmq/Zmq.mqh>
//--- Built-in trade library
#include <Trade/Trade.mqh>

//+------------------------------------------------------------------+
//| Input parameters                                                  |
//+------------------------------------------------------------------+
input int    ZMQ_REP_PORT          = 5555;  // REP socket port (request/reply)
input int    ZMQ_PUB_PORT          = 5556;  // PUB socket port (tick stream)
input int    ZMQ_POLL_INTERVAL_MS  = 1;     // Timer poll interval in ms

//+------------------------------------------------------------------+
//| Global variables                                                  |
//+------------------------------------------------------------------+
Context  g_context("TradeAgent");
Socket   g_repSocket(g_context, ZMQ_REP);
Socket   g_pubSocket(g_context, ZMQ_PUB);
CTrade   g_trade;

string   g_subscribedSymbols[];   // Symbols subscribed for tick streaming
bool     g_initialized = false;

//+------------------------------------------------------------------+
//| Timeframe string to ENUM_TIMEFRAMES conversion                    |
//+------------------------------------------------------------------+
ENUM_TIMEFRAMES StringToTimeframe(string tf)
  {
   StringToUpper(tf);
   if(tf == "M1")  return PERIOD_M1;
   if(tf == "M5")  return PERIOD_M5;
   if(tf == "M15") return PERIOD_M15;
   if(tf == "M30") return PERIOD_M30;
   if(tf == "H1")  return PERIOD_H1;
   if(tf == "H4")  return PERIOD_H4;
   if(tf == "D1")  return PERIOD_D1;
   if(tf == "W1")  return PERIOD_W1;
   if(tf == "MN1") return PERIOD_MN1;
   return PERIOD_CURRENT;
  }

//+------------------------------------------------------------------+
//| Escape a string for JSON output                                   |
//+------------------------------------------------------------------+
string JsonEscape(string s)
  {
   StringReplace(s, "\\", "\\\\");
   StringReplace(s, "\"", "\\\"");
   StringReplace(s, "\n", "\\n");
   StringReplace(s, "\r", "\\r");
   StringReplace(s, "\t", "\\t");
   return s;
  }

//+------------------------------------------------------------------+
//| Format a double to string, stripping trailing zeros               |
//+------------------------------------------------------------------+
string Dbl(double value, int digits = 8)
  {
   if(value == 0.0)
      return "0";
   string s = DoubleToString(value, digits);
   //--- Strip trailing zeros after decimal point
   if(StringFind(s, ".") >= 0)
     {
      int len = StringLen(s);
      while(len > 1 && StringSubstr(s, len - 1, 1) == "0")
        {
         len--;
        }
      if(StringSubstr(s, len - 1, 1) == ".")
         len--;
      s = StringSubstr(s, 0, len);
     }
   return s;
  }

//+------------------------------------------------------------------+
//| Format datetime to ISO 8601 string                                |
//+------------------------------------------------------------------+
string TimeToISO(datetime dt)
  {
   MqlDateTime mdt;
   TimeToStruct(dt, mdt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02d",
                       mdt.year, mdt.mon, mdt.day,
                       mdt.hour, mdt.min, mdt.sec);
  }

//+------------------------------------------------------------------+
//| Build a JSON error response                                       |
//+------------------------------------------------------------------+
string ErrorResponse(string message)
  {
   return "{\"success\":false,\"error\":\"" + JsonEscape(message) + "\"}";
  }

//+------------------------------------------------------------------+
//| Build a JSON success response with data payload                   |
//+------------------------------------------------------------------+
string SuccessResponse(string dataJson)
  {
   return "{\"success\":true,\"data\":" + dataJson + "}";
  }

//+------------------------------------------------------------------+
//| Extract a string value from a JSON key                            |
//| Simple parser — handles: "key":"value" and "key":number           |
//+------------------------------------------------------------------+
string JsonGetString(const string &json, const string key)
  {
   string search = "\"" + key + "\"";
   int pos = StringFind(json, search);
   if(pos < 0)
      return "";
   //--- Move past the key and colon
   pos += StringLen(search);
   //--- Skip whitespace and colon
   int len = StringLen(json);
   while(pos < len)
     {
      string ch = StringSubstr(json, pos, 1);
      if(ch == ":" || ch == " " || ch == "\t" || ch == "\n" || ch == "\r")
        {
         pos++;
         continue;
        }
      break;
     }
   if(pos >= len)
      return "";
   //--- Check if value is quoted string
   if(StringSubstr(json, pos, 1) == "\"")
     {
      pos++; // skip opening quote
      int end = pos;
      while(end < len)
        {
         if(StringSubstr(json, end, 1) == "\\")
           {
            end += 2; // skip escaped char
            continue;
           }
         if(StringSubstr(json, end, 1) == "\"")
            break;
         end++;
        }
      return StringSubstr(json, pos, end - pos);
     }
   //--- Unquoted value (number, bool, null) — read until delimiter
   int end = pos;
   while(end < len)
     {
      string ch = StringSubstr(json, end, 1);
      if(ch == "," || ch == "}" || ch == "]" || ch == " " || ch == "\n" || ch == "\r")
         break;
      end++;
     }
   return StringSubstr(json, pos, end - pos);
  }

//+------------------------------------------------------------------+
//| Extract a double value from JSON                                  |
//+------------------------------------------------------------------+
double JsonGetDouble(const string &json, const string key)
  {
   string val = JsonGetString(json, key);
   if(val == "")
      return 0.0;
   return StringToDouble(val);
  }

//+------------------------------------------------------------------+
//| Extract an integer value from JSON                                |
//+------------------------------------------------------------------+
long JsonGetInt(const string &json, const string key)
  {
   string val = JsonGetString(json, key);
   if(val == "")
      return 0;
   return StringToInteger(val);
  }

//+------------------------------------------------------------------+
//| Extract a JSON array of strings: "key":["a","b","c"]             |
//+------------------------------------------------------------------+
int JsonGetStringArray(const string &json, const string key, string &result[])
  {
   ArrayResize(result, 0);
   string search = "\"" + key + "\"";
   int pos = StringFind(json, search);
   if(pos < 0)
      return 0;
   pos += StringLen(search);
   //--- Find opening bracket
   int len = StringLen(json);
   while(pos < len && StringSubstr(json, pos, 1) != "[")
      pos++;
   if(pos >= len)
      return 0;
   pos++; // skip [
   //--- Parse strings from the array
   int count = 0;
   while(pos < len)
     {
      //--- Skip whitespace and commas
      string ch = StringSubstr(json, pos, 1);
      if(ch == " " || ch == "," || ch == "\t" || ch == "\n" || ch == "\r")
        {
         pos++;
         continue;
        }
      if(ch == "]")
         break;
      if(ch == "\"")
        {
         pos++; // skip opening quote
         int end = pos;
         while(end < len)
           {
            if(StringSubstr(json, end, 1) == "\\")
              {
               end += 2;
               continue;
              }
            if(StringSubstr(json, end, 1) == "\"")
               break;
            end++;
           }
         count++;
         ArrayResize(result, count);
         result[count - 1] = StringSubstr(json, pos, end - pos);
         pos = end + 1; // skip closing quote
        }
      else
        {
         pos++;
        }
     }
   return count;
  }

//+------------------------------------------------------------------+
//| Extract the "params" sub-object from JSON                        |
//+------------------------------------------------------------------+
string JsonGetObject(const string &json, const string key)
  {
   string search = "\"" + key + "\"";
   int pos = StringFind(json, search);
   if(pos < 0)
      return "{}";
   pos += StringLen(search);
   int len = StringLen(json);
   //--- Find opening brace
   while(pos < len && StringSubstr(json, pos, 1) != "{" && StringSubstr(json, pos, 1) != "[")
      pos++;
   if(pos >= len)
      return "{}";
   string openCh = StringSubstr(json, pos, 1);
   string closeCh = (openCh == "{") ? "}" : "]";
   int depth = 1;
   int start = pos;
   pos++;
   while(pos < len && depth > 0)
     {
      string ch = StringSubstr(json, pos, 1);
      if(ch == "\"")
        {
         pos++;
         while(pos < len)
           {
            if(StringSubstr(json, pos, 1) == "\\")
              {
               pos += 2;
               continue;
              }
            if(StringSubstr(json, pos, 1) == "\"")
               break;
            pos++;
           }
        }
      else if(ch == openCh)
         depth++;
      else if(ch == closeCh)
         depth--;
      pos++;
     }
   return StringSubstr(json, start, pos - start);
  }

//+------------------------------------------------------------------+
//| Check if a symbol is valid and available                          |
//+------------------------------------------------------------------+
bool ValidateSymbol(string symbol)
  {
   if(symbol == "")
      return false;
   //--- Attempt to select the symbol in Market Watch
   if(!SymbolSelect(symbol, true))
      return false;
   return SymbolInfoInteger(symbol, SYMBOL_EXIST) != 0;
  }

//+------------------------------------------------------------------+
//| Handle GET_TICK command                                           |
//+------------------------------------------------------------------+
string HandleGetTick(const string &params)
  {
   string symbol = JsonGetString(params, "symbol");
   if(!ValidateSymbol(symbol))
      return ErrorResponse("Invalid or unavailable symbol: " + symbol);

   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick))
      return ErrorResponse("Failed to get tick for " + symbol);

   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   double spread = (tick.ask - tick.bid) / SymbolInfoDouble(symbol, SYMBOL_POINT);

   string data = "{";
   data += "\"symbol\":\"" + symbol + "\",";
   data += "\"bid\":" + Dbl(tick.bid, digits) + ",";
   data += "\"ask\":" + Dbl(tick.ask, digits) + ",";
   data += "\"spread\":" + Dbl(spread, 1) + ",";
   data += "\"timestamp\":\"" + TimeToISO(tick.time) + "\"";
   data += "}";

   return SuccessResponse(data);
  }

//+------------------------------------------------------------------+
//| Handle GET_BARS command                                           |
//+------------------------------------------------------------------+
string HandleGetBars(const string &params)
  {
   string symbol    = JsonGetString(params, "symbol");
   string tfStr     = JsonGetString(params, "timeframe");
   int    count     = (int)JsonGetInt(params, "count");

   if(!ValidateSymbol(symbol))
      return ErrorResponse("Invalid or unavailable symbol: " + symbol);
   if(count <= 0)
      count = 100;
   if(count > 10000)
      count = 10000;

   ENUM_TIMEFRAMES tf = StringToTimeframe(tfStr);
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(symbol, tf, 0, count, rates);
   if(copied <= 0)
      return ErrorResponse("Failed to copy rates for " + symbol + " " + tfStr + ". Error: " + IntegerToString(GetLastError()));

   string data = "[";
   for(int i = 0; i < copied; i++)
     {
      if(i > 0)
         data += ",";
      data += "{";
      data += "\"time\":\"" + TimeToISO(rates[i].time) + "\",";
      data += "\"open\":" + Dbl(rates[i].open, digits) + ",";
      data += "\"high\":" + Dbl(rates[i].high, digits) + ",";
      data += "\"low\":" + Dbl(rates[i].low, digits) + ",";
      data += "\"close\":" + Dbl(rates[i].close, digits) + ",";
      data += "\"volume\":" + IntegerToString(rates[i].tick_volume);
      data += "}";
     }
   data += "]";

   return SuccessResponse(data);
  }

//+------------------------------------------------------------------+
//| Handle GET_INDICATOR command                                      |
//+------------------------------------------------------------------+
string HandleGetIndicator(const string &params)
  {
   string symbol     = JsonGetString(params, "symbol");
   string tfStr      = JsonGetString(params, "timeframe");
   string name       = JsonGetString(params, "name");
   string indParams  = JsonGetObject(params, "params");
   int    count      = (int)JsonGetInt(params, "count");

   if(!ValidateSymbol(symbol))
      return ErrorResponse("Invalid or unavailable symbol: " + symbol);
   if(count <= 0)
      count = 14;
   if(count > 5000)
      count = 5000;

   StringToUpper(name);
   ENUM_TIMEFRAMES tf = StringToTimeframe(tfStr);
   int handle = INVALID_HANDLE;

   //--- Create indicator handle based on name
   if(name == "RSI")
     {
      int period = (int)JsonGetInt(indParams, "period");
      if(period <= 0) period = 14;
      string applied = JsonGetString(indParams, "applied_price");
      ENUM_APPLIED_PRICE ap = PRICE_CLOSE;
      if(applied == "open")    ap = PRICE_OPEN;
      if(applied == "high")    ap = PRICE_HIGH;
      if(applied == "low")     ap = PRICE_LOW;
      if(applied == "median")  ap = PRICE_MEDIAN;
      if(applied == "typical") ap = PRICE_TYPICAL;
      if(applied == "weighted") ap = PRICE_WEIGHTED;
      handle = iRSI(symbol, tf, period, ap);
     }
   else if(name == "EMA")
     {
      int period = (int)JsonGetInt(indParams, "period");
      if(period <= 0) period = 14;
      handle = iMA(symbol, tf, period, 0, MODE_EMA, PRICE_CLOSE);
     }
   else if(name == "SMA")
     {
      int period = (int)JsonGetInt(indParams, "period");
      if(period <= 0) period = 14;
      handle = iMA(symbol, tf, period, 0, MODE_SMA, PRICE_CLOSE);
     }
   else if(name == "MACD")
     {
      int fast   = (int)JsonGetInt(indParams, "fast_ema");
      int slow   = (int)JsonGetInt(indParams, "slow_ema");
      int signal = (int)JsonGetInt(indParams, "signal");
      if(fast <= 0)   fast = 12;
      if(slow <= 0)   slow = 26;
      if(signal <= 0) signal = 9;
      handle = iMACD(symbol, tf, fast, slow, signal, PRICE_CLOSE);
     }
   else if(name == "STOCHASTIC")
     {
      int kPeriod = (int)JsonGetInt(indParams, "k_period");
      int dPeriod = (int)JsonGetInt(indParams, "d_period");
      int slowing = (int)JsonGetInt(indParams, "slowing");
      if(kPeriod <= 0) kPeriod = 5;
      if(dPeriod <= 0) dPeriod = 3;
      if(slowing <= 0) slowing = 3;
      handle = iStochastic(symbol, tf, kPeriod, dPeriod, slowing, MODE_SMA, STO_LOWHIGH);
     }
   else if(name == "BOLLINGER" || name == "BBANDS" || name == "BB")
     {
      int period = (int)JsonGetInt(indParams, "period");
      double deviation = JsonGetDouble(indParams, "deviation");
      if(period <= 0)      period = 20;
      if(deviation <= 0.0) deviation = 2.0;
      handle = iBands(symbol, tf, period, 0, deviation, PRICE_CLOSE);
     }
   else if(name == "ATR")
     {
      int period = (int)JsonGetInt(indParams, "period");
      if(period <= 0) period = 14;
      handle = iATR(symbol, tf, period);
     }
   else if(name == "ADX")
     {
      int period = (int)JsonGetInt(indParams, "period");
      if(period <= 0) period = 14;
      handle = iADX(symbol, tf, period);
     }
   else if(name == "CCI")
     {
      int period = (int)JsonGetInt(indParams, "period");
      if(period <= 0) period = 14;
      handle = iCCI(symbol, tf, period, PRICE_TYPICAL);
     }
   else if(name == "WILLIAMSR" || name == "WPR")
     {
      int period = (int)JsonGetInt(indParams, "period");
      if(period <= 0) period = 14;
      handle = iWPR(symbol, tf, period);
     }
   else
     {
      //--- Custom indicator via iCustom()
      //--- Expects params: "path" (indicator path, e.g. "SMC_Structure" or "Subfolder\\MyInd")
      //---                  "buffers" (int, number of buffers to read)
      //---                  "buffer_names" (string array, names for each buffer)
      //--- Any other params in indParams are passed as indicator inputs (up to 8)
      string customPath = JsonGetString(indParams, "path");
      if(customPath == "")
         customPath = name;  // fallback: use the indicator name as path

      //--- Collect numeric input params (skip our meta-params)
      //--- iCustom supports passing input parameters - we pass common ones
      int    p1 = (int)JsonGetInt(indParams, "p1");
      int    p2 = (int)JsonGetInt(indParams, "p2");
      int    p3 = (int)JsonGetInt(indParams, "p3");
      int    p4 = (int)JsonGetInt(indParams, "p4");
      double d1 = JsonGetDouble(indParams, "d1");
      double d2 = JsonGetDouble(indParams, "d2");

      //--- Determine which iCustom overload to use based on provided params
      if(d1 != 0 && d2 != 0)
         handle = iCustom(symbol, tf, customPath, p1, p2, p3, p4, d1, d2);
      else if(d1 != 0)
         handle = iCustom(symbol, tf, customPath, p1, p2, p3, p4, d1);
      else if(p4 != 0)
         handle = iCustom(symbol, tf, customPath, p1, p2, p3, p4);
      else if(p3 != 0)
         handle = iCustom(symbol, tf, customPath, p1, p2, p3);
      else if(p2 != 0)
         handle = iCustom(symbol, tf, customPath, p1, p2);
      else if(p1 != 0)
         handle = iCustom(symbol, tf, customPath, p1);
      else
         handle = iCustom(symbol, tf, customPath);
     }

   if(handle == INVALID_HANDLE)
      return ErrorResponse("Failed to create indicator handle for " + name + ". Error: " + IntegerToString(GetLastError()));

   //--- Wait for indicator data to be calculated
   //--- Custom indicators may need more time than built-ins
   int waitAttempts = 200;
   while(BarsCalculated(handle) <= 0 && waitAttempts > 0)
     {
      Sleep(50);
      waitAttempts--;
     }

   if(BarsCalculated(handle) <= 0)
     {
      IndicatorRelease(handle);
      return ErrorResponse("Indicator " + name + " has no calculated data. Bars calculated: 0");
     }

   //--- Determine how many buffers to read
   int numBuffers = 1;
   string bufferNames[];

   if(name == "MACD")
     {
      numBuffers = 2;
      ArrayResize(bufferNames, 2);
      bufferNames[0] = "macd";
      bufferNames[1] = "signal";
     }
   else if(name == "STOCHASTIC")
     {
      numBuffers = 2;
      ArrayResize(bufferNames, 2);
      bufferNames[0] = "k";
      bufferNames[1] = "d";
     }
   else if(name == "BOLLINGER" || name == "BBANDS" || name == "BB")
     {
      numBuffers = 3;
      ArrayResize(bufferNames, 3);
      bufferNames[0] = "middle";
      bufferNames[1] = "upper";
      bufferNames[2] = "lower";
     }
   else if(name == "ADX")
     {
      numBuffers = 3;
      ArrayResize(bufferNames, 3);
      bufferNames[0] = "adx";
      bufferNames[1] = "plus_di";
      bufferNames[2] = "minus_di";
     }
   else
     {
      //--- Custom indicator: check for buffer_names and buffers params
      string customBufNames[];
      int customBufCount = JsonGetStringArray(indParams, "buffer_names", customBufNames);
      int requestedBuffers = (int)JsonGetInt(indParams, "buffers");

      if(customBufCount > 0)
        {
         numBuffers = customBufCount;
         ArrayResize(bufferNames, numBuffers);
         for(int bn = 0; bn < numBuffers; bn++)
            bufferNames[bn] = customBufNames[bn];
        }
      else if(requestedBuffers > 0)
        {
         numBuffers = MathMin(requestedBuffers, 20);
         ArrayResize(bufferNames, numBuffers);
         for(int bn = 0; bn < numBuffers; bn++)
            bufferNames[bn] = "buf" + IntegerToString(bn);
        }
      else
        {
         //--- Default: read single buffer
         ArrayResize(bufferNames, 1);
         bufferNames[0] = "value";
        }
     }

   //--- Copy buffers
   string data = "[";
   for(int i = 0; i < count; i++)
     {
      if(i > 0)
         data += ",";
      data += "{";
      bool firstBuf = true;
      for(int b = 0; b < numBuffers; b++)
        {
         double buf[];
         ArraySetAsSeries(buf, true);
         int copied = CopyBuffer(handle, b, i, 1, buf);
         if(!firstBuf)
            data += ",";
         firstBuf = false;
         if(copied > 0)
            data += "\"" + bufferNames[b] + "\":" + Dbl(buf[0]);
         else
            data += "\"" + bufferNames[b] + "\":null";
        }
      data += "}";
     }
   data += "]";

   IndicatorRelease(handle);
   return SuccessResponse(data);
  }

//+------------------------------------------------------------------+
//| Handle GET_POSITIONS command                                      |
//+------------------------------------------------------------------+
string HandleGetPositions(const string &params)
  {
   string filterSymbol = JsonGetString(params, "symbol");
   int total = PositionsTotal();
   string data = "[";
   bool first = true;

   for(int i = 0; i < total; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      string posSymbol = PositionGetString(POSITION_SYMBOL);

      //--- Apply symbol filter if specified
      if(filterSymbol != "" && posSymbol != filterSymbol)
         continue;

      int digits = (int)SymbolInfoInteger(posSymbol, SYMBOL_DIGITS);

      if(!first)
         data += ",";
      first = false;

      string typeStr = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? "BUY" : "SELL";

      data += "{";
      data += "\"ticket\":" + IntegerToString((long)ticket) + ",";
      data += "\"symbol\":\"" + posSymbol + "\",";
      data += "\"type\":\"" + typeStr + "\",";
      data += "\"volume\":" + Dbl(PositionGetDouble(POSITION_VOLUME), 2) + ",";
      data += "\"open_price\":" + Dbl(PositionGetDouble(POSITION_PRICE_OPEN), digits) + ",";
      data += "\"current_price\":" + Dbl(PositionGetDouble(POSITION_PRICE_CURRENT), digits) + ",";
      data += "\"sl\":" + Dbl(PositionGetDouble(POSITION_SL), digits) + ",";
      data += "\"tp\":" + Dbl(PositionGetDouble(POSITION_TP), digits) + ",";
      data += "\"profit\":" + Dbl(PositionGetDouble(POSITION_PROFIT), 2) + ",";
      data += "\"swap\":" + Dbl(PositionGetDouble(POSITION_SWAP), 2) + ",";
      data += "\"open_time\":\"" + TimeToISO((datetime)PositionGetInteger(POSITION_TIME)) + "\",";
      data += "\"magic\":" + IntegerToString(PositionGetInteger(POSITION_MAGIC)) + ",";
      data += "\"comment\":\"" + JsonEscape(PositionGetString(POSITION_COMMENT)) + "\"";
      data += "}";
     }
   data += "]";

   return SuccessResponse(data);
  }

//+------------------------------------------------------------------+
//| Handle GET_ACCOUNT command                                        |
//+------------------------------------------------------------------+
string HandleGetAccount(const string &params)
  {
   string data = "{";
   data += "\"balance\":" + Dbl(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",";
   data += "\"equity\":" + Dbl(AccountInfoDouble(ACCOUNT_EQUITY), 2) + ",";
   data += "\"margin\":" + Dbl(AccountInfoDouble(ACCOUNT_MARGIN), 2) + ",";
   data += "\"free_margin\":" + Dbl(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2) + ",";
   data += "\"margin_level\":" + Dbl(AccountInfoDouble(ACCOUNT_MARGIN_LEVEL), 2) + ",";
   data += "\"profit\":" + Dbl(AccountInfoDouble(ACCOUNT_PROFIT), 2) + ",";
   data += "\"currency\":\"" + AccountInfoString(ACCOUNT_CURRENCY) + "\",";
   data += "\"leverage\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LEVERAGE)) + ",";
   data += "\"name\":\"" + JsonEscape(AccountInfoString(ACCOUNT_NAME)) + "\",";
   data += "\"server\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\",";
   data += "\"company\":\"" + JsonEscape(AccountInfoString(ACCOUNT_COMPANY)) + "\"";
   data += "}";

   return SuccessResponse(data);
  }

//+------------------------------------------------------------------+
//| Handle OPEN_ORDER command                                         |
//+------------------------------------------------------------------+
string HandleOpenOrder(const string &params)
  {
   string symbol  = JsonGetString(params, "symbol");
   string typeStr = JsonGetString(params, "type");
   double lot     = JsonGetDouble(params, "lot");
   double sl      = JsonGetDouble(params, "sl");
   double tp      = JsonGetDouble(params, "tp");
   string comment = JsonGetString(params, "comment");
   long   magic   = JsonGetInt(params, "magic");

   if(!ValidateSymbol(symbol))
      return ErrorResponse("Invalid or unavailable symbol: " + symbol);

   StringToUpper(typeStr);
   ENUM_ORDER_TYPE orderType;
   if(typeStr == "BUY")
      orderType = ORDER_TYPE_BUY;
   else if(typeStr == "SELL")
      orderType = ORDER_TYPE_SELL;
   else
      return ErrorResponse("Invalid order type: " + typeStr + ". Use BUY or SELL.");

   if(lot <= 0.0)
      return ErrorResponse("Invalid lot size: " + Dbl(lot));

   //--- Validate lot against symbol limits
   double minLot  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double lotStep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

   if(lot < minLot)
      return ErrorResponse("Lot size " + Dbl(lot) + " below minimum " + Dbl(minLot) + " for " + symbol);
   if(lot > maxLot)
      return ErrorResponse("Lot size " + Dbl(lot) + " above maximum " + Dbl(maxLot) + " for " + symbol);

   //--- Normalize lot to step
   lot = MathFloor(lot / lotStep) * lotStep;

   //--- Get current price
   MqlTick tick;
   if(!SymbolInfoTick(symbol, tick))
      return ErrorResponse("Cannot get current price for " + symbol);

   double price = (orderType == ORDER_TYPE_BUY) ? tick.ask : tick.bid;
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);

   //--- Normalize SL/TP
   if(sl != 0.0) sl = NormalizeDouble(sl, digits);
   if(tp != 0.0) tp = NormalizeDouble(tp, digits);

   //--- Set magic number if provided
   if(magic > 0)
      g_trade.SetExpertMagicNumber(magic);

   //--- Set comment if provided
   if(comment == "")
      comment = "TradeAgent";

   //--- Execute market order
   bool result = false;
   if(orderType == ORDER_TYPE_BUY)
      result = g_trade.Buy(lot, symbol, price, sl, tp, comment);
   else
      result = g_trade.Sell(lot, symbol, price, sl, tp, comment);

   if(!result)
     {
      uint retcode = g_trade.ResultRetcode();
      return ErrorResponse("Order failed. Retcode: " + IntegerToString(retcode) +
                           " — " + g_trade.ResultRetcodeDescription());
     }

   uint retcode = g_trade.ResultRetcode();
   if(retcode != TRADE_RETCODE_DONE && retcode != TRADE_RETCODE_PLACED)
     {
      return ErrorResponse("Order not confirmed. Retcode: " + IntegerToString(retcode) +
                           " — " + g_trade.ResultRetcodeDescription());
     }

   ulong ticket = g_trade.ResultOrder();

   string data = "{";
   data += "\"ticket\":" + IntegerToString((long)ticket) + ",";
   data += "\"symbol\":\"" + symbol + "\",";
   data += "\"type\":\"" + typeStr + "\",";
   data += "\"volume\":" + Dbl(lot, 2) + ",";
   data += "\"price\":" + Dbl(g_trade.ResultPrice(), digits) + ",";
   data += "\"sl\":" + Dbl(sl, digits) + ",";
   data += "\"tp\":" + Dbl(tp, digits) + ",";
   data += "\"retcode\":" + IntegerToString(retcode);
   data += "}";

   return SuccessResponse(data);
  }

//+------------------------------------------------------------------+
//| Handle CLOSE_ORDER command                                        |
//+------------------------------------------------------------------+
string HandleCloseOrder(const string &params)
  {
   long ticket = JsonGetInt(params, "ticket");
   if(ticket <= 0)
      return ErrorResponse("Invalid ticket number");

   //--- Check if position exists
   if(!PositionSelectByTicket((ulong)ticket))
      return ErrorResponse("Position with ticket " + IntegerToString(ticket) + " not found");

   string symbol = PositionGetString(POSITION_SYMBOL);
   double volume = PositionGetDouble(POSITION_VOLUME);

   if(!g_trade.PositionClose((ulong)ticket))
     {
      uint retcode = g_trade.ResultRetcode();
      return ErrorResponse("Failed to close position " + IntegerToString(ticket) +
                           ". Retcode: " + IntegerToString(retcode) +
                           " — " + g_trade.ResultRetcodeDescription());
     }

   uint retcode = g_trade.ResultRetcode();
   if(retcode != TRADE_RETCODE_DONE)
      return ErrorResponse("Close not confirmed. Retcode: " + IntegerToString(retcode) +
                           " — " + g_trade.ResultRetcodeDescription());

   string data = "{";
   data += "\"ticket\":" + IntegerToString(ticket) + ",";
   data += "\"symbol\":\"" + symbol + "\",";
   data += "\"volume\":" + Dbl(volume, 2) + ",";
   data += "\"retcode\":" + IntegerToString(retcode);
   data += "}";

   return SuccessResponse(data);
  }

//+------------------------------------------------------------------+
//| Handle MODIFY_ORDER command                                       |
//+------------------------------------------------------------------+
string HandleModifyOrder(const string &params)
  {
   long   ticket = JsonGetInt(params, "ticket");
   double sl     = JsonGetDouble(params, "sl");
   double tp     = JsonGetDouble(params, "tp");

   if(ticket <= 0)
      return ErrorResponse("Invalid ticket number");

   if(!PositionSelectByTicket((ulong)ticket))
      return ErrorResponse("Position with ticket " + IntegerToString(ticket) + " not found");

   string symbol = PositionGetString(POSITION_SYMBOL);
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);

   if(sl != 0.0) sl = NormalizeDouble(sl, digits);
   if(tp != 0.0) tp = NormalizeDouble(tp, digits);

   if(!g_trade.PositionModify((ulong)ticket, sl, tp))
     {
      uint retcode = g_trade.ResultRetcode();
      return ErrorResponse("Failed to modify position " + IntegerToString(ticket) +
                           ". Retcode: " + IntegerToString(retcode) +
                           " — " + g_trade.ResultRetcodeDescription());
     }

   uint retcode = g_trade.ResultRetcode();
   if(retcode != TRADE_RETCODE_DONE)
      return ErrorResponse("Modify not confirmed. Retcode: " + IntegerToString(retcode) +
                           " — " + g_trade.ResultRetcodeDescription());

   string data = "{";
   data += "\"ticket\":" + IntegerToString(ticket) + ",";
   data += "\"symbol\":\"" + symbol + "\",";
   data += "\"sl\":" + Dbl(sl, digits) + ",";
   data += "\"tp\":" + Dbl(tp, digits) + ",";
   data += "\"retcode\":" + IntegerToString(retcode);
   data += "}";

   return SuccessResponse(data);
  }

//+------------------------------------------------------------------+
//| Handle GET_HISTORY command                                        |
//+------------------------------------------------------------------+
string HandleGetHistory(const string &params)
  {
   string fromStr = JsonGetString(params, "from_date");
   string toStr   = JsonGetString(params, "to_date");

   datetime fromDate = 0;
   datetime toDate   = TimeCurrent();

   //--- Parse dates (expect ISO format YYYY-MM-DD or YYYY.MM.DD or YYYY-MM-DDTHH:MM:SS)
   if(fromStr != "")
     {
      StringReplace(fromStr, "T", " ");
      StringReplace(fromStr, "-", ".");
      fromDate = StringToTime(fromStr);
     }
   if(toStr != "")
     {
      StringReplace(toStr, "T", " ");
      StringReplace(toStr, "-", ".");
      toDate = StringToTime(toStr);
     }

   //--- Select history range
   if(!HistorySelect(fromDate, toDate))
      return ErrorResponse("Failed to select history range");

   int total = HistoryDealsTotal();
   string data = "[";
   bool first = true;

   for(int i = 0; i < total; i++)
     {
      ulong dealTicket = HistoryDealGetTicket(i);
      if(dealTicket == 0)
         continue;

      //--- Skip balance/credit operations — only include actual trades
      ENUM_DEAL_TYPE dealType = (ENUM_DEAL_TYPE)HistoryDealGetInteger(dealTicket, DEAL_TYPE);
      if(dealType != DEAL_TYPE_BUY && dealType != DEAL_TYPE_SELL)
         continue;

      string dealSymbol = HistoryDealGetString(dealTicket, DEAL_SYMBOL);
      int digits = (int)SymbolInfoInteger(dealSymbol, SYMBOL_DIGITS);
      if(digits <= 0) digits = 5;

      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
      string entryStr = "UNKNOWN";
      if(entry == DEAL_ENTRY_IN)    entryStr = "IN";
      if(entry == DEAL_ENTRY_OUT)   entryStr = "OUT";
      if(entry == DEAL_ENTRY_INOUT) entryStr = "INOUT";

      if(!first)
         data += ",";
      first = false;

      data += "{";
      data += "\"ticket\":" + IntegerToString((long)dealTicket) + ",";
      data += "\"order\":" + IntegerToString((long)HistoryDealGetInteger(dealTicket, DEAL_ORDER)) + ",";
      data += "\"symbol\":\"" + dealSymbol + "\",";
      data += "\"type\":\"" + ((dealType == DEAL_TYPE_BUY) ? "BUY" : "SELL") + "\",";
      data += "\"entry\":\"" + entryStr + "\",";
      data += "\"volume\":" + Dbl(HistoryDealGetDouble(dealTicket, DEAL_VOLUME), 2) + ",";
      data += "\"price\":" + Dbl(HistoryDealGetDouble(dealTicket, DEAL_PRICE), digits) + ",";
      data += "\"profit\":" + Dbl(HistoryDealGetDouble(dealTicket, DEAL_PROFIT), 2) + ",";
      data += "\"swap\":" + Dbl(HistoryDealGetDouble(dealTicket, DEAL_SWAP), 2) + ",";
      data += "\"commission\":" + Dbl(HistoryDealGetDouble(dealTicket, DEAL_COMMISSION), 2) + ",";
      data += "\"time\":\"" + TimeToISO((datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME)) + "\",";
      data += "\"magic\":" + IntegerToString(HistoryDealGetInteger(dealTicket, DEAL_MAGIC)) + ",";
      data += "\"comment\":\"" + JsonEscape(HistoryDealGetString(dealTicket, DEAL_COMMENT)) + "\"";
      data += "}";
     }
   data += "]";

   return SuccessResponse(data);
  }

//+------------------------------------------------------------------+
//| Handle SUBSCRIBE command                                          |
//+------------------------------------------------------------------+
string HandleSubscribe(const string &params)
  {
   string symbols[];
   int count = JsonGetStringArray(params, "symbols", symbols);
   if(count <= 0)
      return ErrorResponse("No symbols provided. Use {\"symbols\":[\"XAUUSD\",\"EURUSD\"]}");

   //--- Validate all symbols first
   string invalid = "";
   for(int i = 0; i < count; i++)
     {
      if(!ValidateSymbol(symbols[i]))
        {
         if(invalid != "") invalid += ", ";
         invalid += symbols[i];
        }
     }
   if(invalid != "")
      return ErrorResponse("Invalid or unavailable symbols: " + invalid);

   //--- Replace subscription list
   ArrayResize(g_subscribedSymbols, count);
   for(int i = 0; i < count; i++)
     {
      g_subscribedSymbols[i] = symbols[i];
      //--- Enable Market Watch for each symbol
      SymbolSelect(symbols[i], true);
      //--- Request tick events by subscribing to BookAdd (ensures OnTick fires)
      MarketBookAdd(symbols[i]);
     }

   string symList = "[";
   for(int i = 0; i < count; i++)
     {
      if(i > 0) symList += ",";
      symList += "\"" + symbols[i] + "\"";
     }
   symList += "]";

   string data = "{\"subscribed\":" + symList + ",\"count\":" + IntegerToString(count) + "}";
   return SuccessResponse(data);
  }

//+------------------------------------------------------------------+
//| Route incoming JSON command to the correct handler                |
//+------------------------------------------------------------------+
string ProcessCommand(const string &message)
  {
   string command = JsonGetString(message, "command");
   string params  = JsonGetObject(message, "params");

   StringToUpper(command);

   if(command == "GET_TICK")       return HandleGetTick(params);
   if(command == "GET_BARS")       return HandleGetBars(params);
   if(command == "GET_INDICATOR")  return HandleGetIndicator(params);
   if(command == "GET_POSITIONS")  return HandleGetPositions(params);
   if(command == "GET_ACCOUNT")    return HandleGetAccount(params);
   if(command == "OPEN_ORDER")     return HandleOpenOrder(params);
   if(command == "CLOSE_ORDER")    return HandleCloseOrder(params);
   if(command == "MODIFY_ORDER")   return HandleModifyOrder(params);
   if(command == "GET_HISTORY")    return HandleGetHistory(params);
   if(command == "SUBSCRIBE")      return HandleSubscribe(params);
   if(command == "PING")           return SuccessResponse("\"pong\"");

   return ErrorResponse("Unknown command: " + command);
  }

//+------------------------------------------------------------------+
//| Expert initialization function                                    |
//+------------------------------------------------------------------+
int OnInit()
  {
   //--- Configure trade execution
   g_trade.SetDeviationInPoints(10);
   g_trade.SetTypeFilling(ORDER_FILLING_IOC);
   g_trade.SetAsyncMode(false);

   //--- Bind REP socket
   string repAddr = "tcp://*:" + IntegerToString(ZMQ_REP_PORT);
   if(!g_repSocket.bind(repAddr))
     {
      Print("[TradeAgent] ERROR: Failed to bind REP socket on ", repAddr, ". Error: ", GetLastError());
      return INIT_FAILED;
     }
   //--- Set REP socket options for non-blocking polling
   g_repSocket.setReceiveTimeout(1);
   g_repSocket.setLinger(0);
   Print("[TradeAgent] REP socket bound on ", repAddr);

   //--- Bind PUB socket
   string pubAddr = "tcp://*:" + IntegerToString(ZMQ_PUB_PORT);
   if(!g_pubSocket.bind(pubAddr))
     {
      Print("[TradeAgent] ERROR: Failed to bind PUB socket on ", pubAddr, ". Error: ", GetLastError());
      g_repSocket.unbind(repAddr);
      return INIT_FAILED;
     }
   g_pubSocket.setLinger(0);
   Print("[TradeAgent] PUB socket bound on ", pubAddr);

   //--- Start timer for REP socket polling
   if(!EventSetMillisecondTimer(ZMQ_POLL_INTERVAL_MS))
     {
      Print("[TradeAgent] WARNING: Failed to set millisecond timer. Falling back to 1s timer.");
      EventSetTimer(1);
     }

   g_initialized = true;
   Print("[TradeAgent] Initialized successfully. REP=", ZMQ_REP_PORT, " PUB=", ZMQ_PUB_PORT);
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| Expert deinitialization function                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();

   //--- Unsubscribe from MarketBook for all subscribed symbols
   for(int i = 0; i < ArraySize(g_subscribedSymbols); i++)
      MarketBookRelease(g_subscribedSymbols[i]);
   ArrayResize(g_subscribedSymbols, 0);

   //--- Close sockets
   string repAddr = "tcp://*:" + IntegerToString(ZMQ_REP_PORT);
   string pubAddr = "tcp://*:" + IntegerToString(ZMQ_PUB_PORT);
   g_repSocket.unbind(repAddr);
   g_pubSocket.unbind(pubAddr);

   g_initialized = false;
   Print("[TradeAgent] Deinitialized. Reason: ", reason);
  }

//+------------------------------------------------------------------+
//| Timer function — polls REP socket for incoming commands           |
//+------------------------------------------------------------------+
void OnTimer()
  {
   if(!g_initialized)
      return;

   //--- Poll for incoming messages (non-blocking via receive timeout)
   ZmqMsg request;
   if(!g_repSocket.recv(request, true))  // true = non-blocking
      return;

   //--- Extract message string
   string message = request.getData();
   if(message == "" || message == NULL)
     {
      //--- Must send a reply on REP socket even for empty messages
      ZmqMsg reply(ErrorResponse("Empty message received"));
      g_repSocket.send(reply);
      return;
     }

   //--- Process command and send reply
   string response = ProcessCommand(message);

   ZmqMsg reply(response);
   if(!g_repSocket.send(reply))
     {
      Print("[TradeAgent] ERROR: Failed to send reply. Error: ", GetLastError());
     }
  }

//+------------------------------------------------------------------+
//| Tick function — publishes tick data for subscribed symbols        |
//+------------------------------------------------------------------+
void OnTick()
  {
   if(!g_initialized)
      return;

   int subCount = ArraySize(g_subscribedSymbols);
   if(subCount == 0)
      return;

   for(int i = 0; i < subCount; i++)
     {
      string symbol = g_subscribedSymbols[i];
      MqlTick tick;

      if(!SymbolInfoTick(symbol, tick))
         continue;

      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);

      string json = "{";
      json += "\"symbol\":\"" + symbol + "\",";
      json += "\"bid\":" + Dbl(tick.bid, digits) + ",";
      json += "\"ask\":" + Dbl(tick.ask, digits) + ",";
      json += "\"timestamp\":\"" + TimeToISO(tick.time) + "\"";
      json += "}";

      ZmqMsg msg(json);
      g_pubSocket.send(msg, true);  // true = non-blocking
     }
  }

//+------------------------------------------------------------------+
//| BookEvent function — fires when subscribed symbol depths update   |
//| This ensures we get tick data for symbols beyond chart symbol     |
//+------------------------------------------------------------------+
void OnBookEvent(const string &symbol)
  {
   if(!g_initialized)
      return;

   //--- Check if this symbol is subscribed
   int subCount = ArraySize(g_subscribedSymbols);
   for(int i = 0; i < subCount; i++)
     {
      if(g_subscribedSymbols[i] == symbol)
        {
         MqlTick tick;
         if(!SymbolInfoTick(symbol, tick))
            return;

         int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);

         string json = "{";
         json += "\"symbol\":\"" + symbol + "\",";
         json += "\"bid\":" + Dbl(tick.bid, digits) + ",";
         json += "\"ask\":" + Dbl(tick.ask, digits) + ",";
         json += "\"timestamp\":\"" + TimeToISO(tick.time) + "\"";
         json += "}";

         ZmqMsg msg(json);
         g_pubSocket.send(msg, true);
         return;
        }
     }
  }
//+------------------------------------------------------------------+
