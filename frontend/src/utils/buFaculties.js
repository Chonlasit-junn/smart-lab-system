// ข้อมูลคณะและสาขาวิชาของมหาวิทยาลัยกรุงเทพ
// อ้างอิงจากโครงสร้างคณะปัจจุบัน — อัปเดตได้ตามปีการศึกษา

export const BU_FACULTIES = [
  {
    id: 'business',
    name_th: 'คณะบริหารธุรกิจ',
    name_en: 'School of Business Administration',
    departments: [
      { id: 'marketing',   name_th: 'การตลาด',                   name_en: 'Marketing' },
      { id: 'management',  name_th: 'การจัดการ',                  name_en: 'Management' },
      { id: 'finance',     name_th: 'การเงิน',                   name_en: 'Finance' },
      { id: 'logistics',   name_th: 'การจัดการโลจิสติกส์',        name_en: 'Logistics Management' },
      { id: 'entre',       name_th: 'การประกอบการ',               name_en: 'Entrepreneurship' },
      { id: 'hotel',       name_th: 'การจัดการธุรกิจโรงแรม',      name_en: 'Hotel Business Management' },
      { id: 'airline',     name_th: 'ธุรกิจการบิน',               name_en: 'Airline Business' },
    ],
  },
  {
    id: 'communication',
    name_th: 'คณะนิเทศศาสตร์',
    name_en: 'School of Communication Arts',
    departments: [
      { id: 'advertising',  name_th: 'การโฆษณา',                  name_en: 'Advertising' },
      { id: 'pr',           name_th: 'การประชาสัมพันธ์',           name_en: 'Public Relations' },
      { id: 'film',         name_th: 'ภาพยนตร์และสื่อดิจิทัล',    name_en: 'Film and Digital Media' },
      { id: 'radio_tv',     name_th: 'วิทยุกระจายเสียงและโทรทัศน์', name_en: 'Broadcasting' },
      { id: 'journalism',   name_th: 'วารสารศาสตร์',               name_en: 'Journalism' },
    ],
  },
  {
    id: 'engineering',
    name_th: 'คณะวิศวกรรมศาสตร์',
    name_en: 'School of Engineering',
    departments: [
      { id: 'computer_eng',   name_th: 'วิศวกรรมคอมพิวเตอร์',     name_en: 'Computer Engineering' },
      { id: 'electrical',     name_th: 'วิศวกรรมไฟฟ้า',           name_en: 'Electrical Engineering' },
      { id: 'industrial',     name_th: 'วิศวกรรมอุตสาหการ',        name_en: 'Industrial Engineering' },
      { id: 'civil',          name_th: 'วิศวกรรมโยธา',            name_en: 'Civil Engineering' },
      { id: 'robotics',       name_th: 'วิศวกรรมหุ่นยนต์และระบบอัตโนมัติ', name_en: 'Robotics and Automation Engineering' },
    ],
  },
  {
    id: 'it',
    name_th: 'คณะเทคโนโลยีสารสนเทศและนวัตกรรม',
    name_en: 'School of Information Technology and Innovation',
    departments: [
      { id: 'cs',           name_th: 'วิทยาการคอมพิวเตอร์',       name_en: 'Computer Science' },
      { id: 'it',           name_th: 'เทคโนโลยีสารสนเทศ',         name_en: 'Information Technology' },
      { id: 'data_sci',     name_th: 'วิทยาศาสตร์ข้อมูล',         name_en: 'Data Science' },
      { id: 'cyber',        name_th: 'ความมั่นคงไซเบอร์',          name_en: 'Cyber Security' },
      { id: 'game_dev',     name_th: 'การพัฒนาเกม',               name_en: 'Game Development' },
      { id: 'digital_inn',  name_th: 'นวัตกรรมดิจิทัล',           name_en: 'Digital Innovation' },
    ],
  },
  {
    id: 'architecture',
    name_th: 'คณะสถาปัตยกรรมศาสตร์',
    name_en: 'School of Architecture',
    departments: [
      { id: 'architecture', name_th: 'สถาปัตยกรรม',              name_en: 'Architecture' },
      { id: 'interior',     name_th: 'การออกแบบภายใน',            name_en: 'Interior Design' },
      { id: 'product',      name_th: 'การออกแบบผลิตภัณฑ์',        name_en: 'Product Design' },
      { id: 'fashion',      name_th: 'การออกแบบแฟชั่น',           name_en: 'Fashion Design' },
    ],
  },
  {
    id: 'humanities',
    name_th: 'คณะมนุษยศาสตร์',
    name_en: 'School of Humanities',
    departments: [
      { id: 'english',   name_th: 'ภาษาอังกฤษ',                  name_en: 'English' },
      { id: 'chinese',   name_th: 'ภาษาจีน',                     name_en: 'Chinese' },
      { id: 'japanese',  name_th: 'ภาษาญี่ปุ่น',                  name_en: 'Japanese' },
    ],
  },
  {
    id: 'finearts',
    name_th: 'คณะศิลปกรรมศาสตร์',
    name_en: 'School of Fine and Applied Arts',
    departments: [
      { id: 'visual',      name_th: 'ทัศนศิลป์',                  name_en: 'Visual Arts' },
      { id: 'digital_art', name_th: 'ศิลปะดิจิทัล',              name_en: 'Digital Arts' },
      { id: 'music',       name_th: 'ดนตรีร่วมสมัย',              name_en: 'Contemporary Music' },
    ],
  },
  {
    id: 'law',
    name_th: 'คณะนิติศาสตร์',
    name_en: 'School of Law',
    departments: [
      { id: 'law', name_th: 'นิติศาสตร์', name_en: 'Law' },
    ],
  },
  {
    id: 'accounting',
    name_th: 'คณะการบัญชี',
    name_en: 'School of Accounting',
    departments: [
      { id: 'accounting', name_th: 'การบัญชี', name_en: 'Accounting' },
    ],
  },
  {
    id: 'economics',
    name_th: 'คณะเศรษฐศาสตร์',
    name_en: 'School of Economics',
    departments: [
      { id: 'economics', name_th: 'เศรษฐศาสตร์',           name_en: 'Economics' },
      { id: 'econ_data', name_th: 'เศรษฐศาสตร์ดิจิทัล',    name_en: 'Digital Economics' },
    ],
  },
];