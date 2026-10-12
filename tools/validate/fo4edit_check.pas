{
  FO4Edit's "Check for errors" over one plugin, run headless by tools/validate/fo4_check.py.
  Reads the plugin's name from fo4_check_target.txt in the data folder and writes one line per
  error to fo4_check_result.txt there: record | element path -> error.
}
unit FO4Check;

var
  Lines: TStringList;

procedure CheckElement(e: IInterface; rec: string);
var
  error: string;
  i: Integer;
begin
  error := Check(e);
  if error <> '' then
    Lines.Add(rec + ' | ' + Path(e) + ' -> ' + error);
  for i := 0 to ElementCount(e) - 1 do
    CheckElement(ElementByIndex(e, i), rec);
end;

function Initialize: Integer;
var
  target: TStringList;
  f, rec: IInterface;
  i, j: Integer;
begin
  Lines := TStringList.Create;
  target := TStringList.Create;
  target.LoadFromFile(DataPath + 'fo4_check_target.txt');
  for i := 0 to FileCount - 1 do begin
    f := FileByIndex(i);
    if SameText(GetFileName(f), Trim(target[0])) then begin
      Lines.Add('# checked ' + GetFileName(f) + ': ' + IntToStr(RecordCount(f)) + ' records');
      for j := 0 to RecordCount(f) - 1 do begin
        rec := RecordByIndex(f, j);
        CheckElement(rec, Name(rec));
      end;
    end;
  end;
  Lines.SaveToFile(DataPath + 'fo4_check_result.txt');
  Result := 0;
end;

end.
