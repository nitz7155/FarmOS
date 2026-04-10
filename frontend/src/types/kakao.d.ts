interface DaumPostcodeData {
  zonecode: string;
  roadAddress: string;
  jibunAddress: string;
  autoRoadAddress: string;
  autoJibunAddress: string;
  buildingName: string;
  apartment: 'Y' | 'N';
  bname: string;
  bname1: string;
  userSelectedType: 'R' | 'J';
}

declare namespace daum {
  class Postcode {
    constructor(options: { oncomplete: (data: DaumPostcodeData) => void });
    open(): void;
  }
}
