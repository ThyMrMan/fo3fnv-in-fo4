package f3nv.casino
{
   // xorshift32, the same numbers as tests/casino/model.py's Rng.
   public class Rng
   {
      public static const SEED_ZERO:uint = 0x2545F491;

      private var state:uint;

      public function Rng(seed:uint)
      {
         state = seed != 0 ? seed : SEED_ZERO;
      }

      public function next() : uint
      {
         var x:uint = state;
         x ^= x << 13;
         x ^= x >>> 17;
         x ^= x << 5;
         state = x;
         return x;
      }

      // A number from 0 to n - 1.
      public function below(n:int) : int
      {
         return int(next() % uint(n));
      }
   }
}
