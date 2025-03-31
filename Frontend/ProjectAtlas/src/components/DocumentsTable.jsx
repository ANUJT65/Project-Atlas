import React from 'react';

const DocumentsTable = () => {
  const documents = [
    { name: 'Doc1.pdf', version: '1.0', uploadedBy: 'Alice', project: 'Project A', date: '2025-03-29' },
    { name: 'Doc2.docx', version: '2.1', uploadedBy: 'Bob', project: 'Project B', date: '2025-03-28' },
    { name: 'Doc3.xlsx', version: '3.0', uploadedBy: 'Charlie', project: 'Project C', date: '2025-03-27' }
  ];

  return (
    <div className="overflow-x-auto p-4">
      <table className="text-sm w-full border-black bg-white">
        <thead>
          <tr className="bg-gray-100">
            <th className="border-b border-black p-2">Document Name</th>
            <th className="border-b border-black p-2">Version</th>
            <th className="border-b border-black p-2">Uploaded By</th>
            <th className="border-b border-black p-2">Project Name</th>
            <th className="border-b border-black p-2">Uploaded On</th>
            <th className="border-b border-black p-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc, index) => (
            <tr key={index} className="text-center">
              <td className=" border-black p-2">{doc.name}</td>
              <td className=" border-black p-2">{doc.version}</td>
              <td className=" border-black p-2">{doc.uploadedBy}</td>
              <td className=" border-black p-2">{doc.project}</td>
              <td className=" border-black p-2">{doc.date}</td>
              <td className=" border-black p-2 flex justify-center gap-2">
                <button className="bg-[#00AEEF] text-white px-3 py-1 rounded">View</button>
                <button className="bg-[#00AEEF] text-white px-3 py-1 rounded">Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default DocumentsTable;