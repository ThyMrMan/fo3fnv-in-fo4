ScriptName F3NV_Array Hidden
{xNVSE arrays for converted scripts. An array is a Var[] whose element 0 is its kind: 1 Array (a list,
keys 0..n-1, values from element 1), 2 Map (numeric keys) or 3 StringMap; a map stores key, value pairs
from element 1, kept in key order as xNVSE iterates them. None is xNVSE's null array.
See: docs/fork/nvse_script_language.md#arrays}

;-- Construction ---------------------------------------------------------------

Var[] Function Construct(String asKind) Global
  {ar_Construct: a new empty "Array", "Map" or "StringMap".}
  Var[] arr = new Var[1]
  arr[0] = 1
  If asKind == "Map"
    arr[0] = 2
  ElseIf asKind == "StringMap"
    arr[0] = 3
  EndIf
  Return arr
EndFunction

Var[] Function List(Int aiCount, Var a0, Var a1, Var a2, Var a3, Var a4, \
    Var a5, Var a6, Var a7, Var a8, Var a9, Var a10, Var a11, \
    Var a12, Var a13, Var a14, Var a15, Var a16, Var a17, \
    Var a18, Var a19) Global
  {ar_List: an Array of the first aiCount arguments (xNVSE takes at most 20).}
  Var[] items = new Var[20]
  items[0] = a0
  items[1] = a1
  items[2] = a2
  items[3] = a3
  items[4] = a4
  items[5] = a5
  items[6] = a6
  items[7] = a7
  items[8] = a8
  items[9] = a9
  items[10] = a10
  items[11] = a11
  items[12] = a12
  items[13] = a13
  items[14] = a14
  items[15] = a15
  items[16] = a16
  items[17] = a17
  items[18] = a18
  items[19] = a19
  Var[] arr = Construct("Array")
  Int i = 0
  While i < aiCount && i < 20
    arr.Add(items[i])
    i += 1
  EndWhile
  Return arr
EndFunction

Var[] Function FromForms(Form[] akForms) Global
  {An Array holding akForms, for a native that returns a Papyrus array where xNVSE returned one of its own.}
  Var[] arr = Construct("Array")
  Int i = 0
  While i < akForms.Length
    arr.Add(akForms[i])
    i += 1
  EndWhile
  Return arr
EndFunction

Var[] Function Box(Var akValue) Global
  {The & operator: a one-element Array.}
  Var[] arr = Construct("Array")
  arr.Add(akValue)
  Return arr
EndFunction

Var[] Function Copy(Var[] akArray) Global
  {ar_Copy: a new array with the same kind and elements (nested arrays shared).}
  If !akArray
    Return None
  EndIf
  Var[] arr = new Var[1]
  arr[0] = akArray[0]
  Int i = 1
  While i < akArray.Length
    arr.Add(akArray[i])
    i += 1
  EndWhile
  Return arr
EndFunction

;-- Reading --------------------------------------------------------------------

Int Function Kind(Var[] akArray) Global
  {1 Array, 2 Map, 3 StringMap; 0 for the null array.}
  If !akArray
    Return 0
  EndIf
  Return akArray[0] as Int
EndFunction

Int Function Size(Var[] akArray) Global
  {ar_Size: how many elements; -1 for the null array, as xNVSE.}
  Int kind = Kind(akArray)
  If kind == 0
    Return -1
  ElseIf kind == 1
    Return akArray.Length - 1
  EndIf
  Return (akArray.Length - 1) / 2
EndFunction

Int Function Slot(Var[] akArray, Var akKey) Global
  {The element of akArray holding akKey's value, or -1 when it has no such key.}
  Int kind = Kind(akArray)
  If kind == 1
    Int i = akKey as Int
    If i >= 0 && i < akArray.Length - 1
      Return i + 1
    EndIf
    Return -1
  EndIf
  Int j = 1
  While j < akArray.Length
    If SameKey(kind, akArray[j], akKey)
      Return j + 1
    EndIf
    j += 2
  EndWhile
  Return -1
EndFunction

Bool Function SameKey(Int aiKind, Var akA, Var akB) Global
  {Do two map keys name the same element? Numeric keys compare as numbers, string keys ignoring case.}
  If aiKind == 3
    Return (akA as String) == (akB as String)
  EndIf
  Return (akA as Float) == (akB as Float)
EndFunction

Bool Function SameValue(Var akA, Var akB) Global
  {xNVSE's == on two elements: forms by identity, strings ignoring case, everything else as numbers.}
  If akA is Form || akB is Form
    Return (akA as Form) == (akB as Form)
  ElseIf akA is String || akB is String
    Return (akA as String) == (akB as String)
  EndIf
  Return (akA as Float) == (akB as Float)
EndFunction

Bool Function KeyBefore(Int aiKind, Var akA, Var akB) Global
  {Does map key akA sort before akB?}
  If aiKind == 3
    Return (akA as String) < (akB as String)
  EndIf
  Return (akA as Float) < (akB as Float)
EndFunction

Var Function Get(Var[] akArray, Var akKey) Global
  {arr[key]: the element's value, None when the key is absent.}
  Int slot = Slot(akArray, akKey)
  If slot < 0
    Return None
  EndIf
  Return akArray[slot]
EndFunction

Bool Function HasKey(Var[] akArray, Var akKey) Global
  {ar_HasKey.}
  Return Slot(akArray, akKey) >= 0
EndFunction

Var Function Find(Var akValue, Var[] akArray) Global
  {ar_Find: the key of the first element equal to akValue; ar_BadNumericIndex (-99999), or "" in a StringMap.}
  Int kind = Kind(akArray)
  Int i = 1
  While kind == 1 && i < akArray.Length
    If SameValue(akArray[i], akValue)
      Return i - 1
    EndIf
    i += 1
  EndWhile
  i = 2
  While kind > 1 && i < akArray.Length
    If SameValue(akArray[i], akValue)
      Return akArray[i - 1]
    EndIf
    i += 2
  EndWhile
  If kind == 3
    Return ""
  EndIf
  Return -99999
EndFunction

Var Function KeyAt(Var[] akArray, Int aiIndex) Global
  {The aiIndex-th key in iteration order.}
  If Kind(akArray) == 1
    Return aiIndex
  EndIf
  Return akArray[1 + 2 * aiIndex]
EndFunction

Var Function ValueAt(Var[] akArray, Int aiIndex) Global
  {The aiIndex-th value in iteration order.}
  If Kind(akArray) == 1
    Return akArray[1 + aiIndex]
  EndIf
  Return akArray[2 + 2 * aiIndex]
EndFunction

Var[] Function Iterator(Var[] akArray, Int aiIndex) Global
  {The StringMap a ForEach loop gives its iterator: "key" and "value" of the aiIndex-th element.}
  Var[] it = Construct("StringMap")
  it.Add("key")
  it.Add(KeyAt(akArray, aiIndex))
  it.Add("value")
  it.Add(ValueAt(akArray, aiIndex))
  Return it
EndFunction

Var Function Unbox(Var[] akArray) Global
  {The * operator: a StringMap's "value", else the first element.}
  If Kind(akArray) == 3
    Return Get(akArray, "value")
  ElseIf Size(akArray) > 0
    Return ValueAt(akArray, 0)
  EndIf
  Return None
EndFunction

;-- Writing --------------------------------------------------------------------

Bool Function Set(Var[] akArray, Var akKey, Var akValue) Global
  {arr[key] := value. An Array grows only by writing one past its end, as xNVSE; a map inserts in key order.}
  Int slot = Slot(akArray, akKey)
  If slot >= 0
    akArray[slot] = akValue
    Return True
  EndIf
  Int kind = Kind(akArray)
  If kind == 1
    If (akKey as Int) != akArray.Length - 1
      Return False
    EndIf
    akArray.Add(akValue)
    Return True
  ElseIf kind == 0
    Return False
  EndIf
  Int at = 1
  While at < akArray.Length && KeyBefore(kind, akArray[at], akKey)
    at += 2
  EndWhile
  akArray.Insert(akValue, at)
  akArray.Insert(akKey, at)
  Return True
EndFunction

Bool Function Append(Var[] akArray, Var akValue) Global
  {ar_Append: add to the end of an Array.}
  If Kind(akArray) != 1
    Return False
  EndIf
  akArray.Add(akValue)
  Return True
EndFunction

Int Function Erase(Var[] akArray, Var akKey) Global
  {ar_Erase: remove one key; how many elements went.}
  Int slot = Slot(akArray, akKey)
  If slot < 0
    Return 0
  ElseIf Kind(akArray) == 1
    akArray.Remove(slot)
  Else
    akArray.Remove(slot - 1, 2)
  EndIf
  Return 1
EndFunction

Function Clear(Var[] akArray) Global
  {Empty an array, keeping its kind.}
  If akArray && akArray.Length > 1
    akArray.Remove(1, akArray.Length - 1)
  EndIf
EndFunction
